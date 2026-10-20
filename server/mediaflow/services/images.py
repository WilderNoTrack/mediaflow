"""AI 配图：一整套中文画面描述 → 一次扩写成「统一视觉规范 + 每张提示词」→ 生图服务 → 存到本地 data/images。

一套图必须统一：
- 规范存在 draft.image_spec，每张的提示词都带上同一份；只重出某几张时沿用，不重新定
- 有参考帖原图时，每张照着同一篇参考帖里对应的那张做版式（不会混用好几篇帖子的图）
- 已经有出好的图时（重出某张、补出失败的），把同套里出好的一张也带上当风格参照；
  没有参考帖、要从头出一整套时，先出封面，其余几张带上封面一起出

生图服务抽象成 ImageProvider，默认实现是 grsai 节点（gpt-image-2.5 / nano-banana-2.1，界面里可选）。
要换别家，实现一个 generate(prompt) -> bytes 即可。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4

import httpx
from sqlmodel import Session, col, select

from mediaflow import credentials
from mediaflow.agents import prompts
from mediaflow.config import Settings, get_settings
from mediaflow.domain.models import Account, Draft, DraftImage, ImageStatus, utcnow
from mediaflow.llm.client import LLM, LLMError, complete_json
from mediaflow.services.refs import local_uri, uri_of

logger = logging.getLogger(__name__)


class ImageError(RuntimeError):
    def __init__(self, msg: str, *, retryable: bool = True) -> None:
        super().__init__(msg)
        self.retryable = retryable  # 违规/密钥错误换模型也没用


@dataclass(frozen=True)
class ImageModel:
    id: str
    label: str
    desc: str
    payload: dict


# 都是 grsai 节点上的模型，同一个 Key；都出 3:4 竖图（小红书标准比例）
MODELS: list[ImageModel] = [
    ImageModel("gpt-image-2.5", "GPT Image 2.5",
               "推荐。更像小红书封面：大字标题排版好看、画面有设计感；便宜一点，一张约 1 分钟", {"aspectRatio": "3:4"}),
    ImageModel("nano-banana-2.1", "Nano Banana 2.1",
               "出图快（一张约 20 秒），画面更写实像实拍；贵一点点", {"aspectRatio": "3:4", "imageSize": "1K"}),
]
_MODELS = {m.id: m for m in MODELS}


def image_key() -> str:
    return credentials.get("image_api_key")


def image_model() -> str:
    return credentials.get("image_model") or get_settings().image_model


def image_configured() -> bool:
    return bool(image_key())


def use_refs() -> bool:
    """出图时要不要把对标账号的原图当参考图传上去（默认要）。"""
    return credentials.get("image_refs") != "off"


def _payload(model: str) -> dict:
    m = _MODELS.get(model)
    return dict(m.payload) if m else {"aspectRatio": get_settings().image_size}


class ImageProvider(Protocol):
    async def generate(self, prompt: str, refs: list[str] | None = None) -> bytes: ...


class GrsaiProvider:
    """grsai 生图：提交（同步等结果，没等到就轮询 /result）→ 下载。主模型失败自动换另一个模型重试一次。"""

    def __init__(self, settings: Settings | None = None, *, model: str | None = None, key: str | None = None,
                 fallback: bool = True) -> None:
        self.s = settings or get_settings()
        self.key = key if key is not None else image_key()
        if not self.key:
            raise ImageError("没有配置配图 API Key", retryable=False)
        self.model = model or image_model()
        others = [m.id for m in MODELS if m.id != self.model]
        self.fallback = others[0] if fallback and others else None

    async def generate(self, prompt: str, refs: list[str] | None = None) -> bytes:
        try:
            return await self._one(self.model, prompt, refs)
        except ImageError as e:
            if not self.fallback or not e.retryable:
                raise
            logger.warning("%s 生图失败（%s），换 %s 再试", self.model, e, self.fallback)
            return await self._one(self.fallback, prompt, refs)

    async def _one(self, model: str, prompt: str, refs: list[str] | None = None) -> bytes:
        headers = {"Authorization": f"Bearer {self.key}"}
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.s.image_timeout
        async with httpx.AsyncClient(timeout=httpx.Timeout(self.s.image_timeout, connect=15)) as c:
            try:
                r = await c.post(self.s.image_endpoint, headers=headers, json={
                    "model": model, "prompt": prompt, "replyType": "json", **_payload(model),
                    **({"images": refs} if refs else {})})
            except httpx.HTTPError as e:
                raise ImageError(f"连不上生图服务：{type(e).__name__}") from e
            if r.status_code in (401, 403):
                raise ImageError("配图 API Key 不对或已失效", retryable=False)
            try:
                data = r.json()
            except ValueError:
                raise ImageError(f"生图接口 HTTP {r.status_code}：{r.text[:200]}") from None
            data = data.get("data") if isinstance(data.get("data"), dict) else data
            result_url = self.s.image_endpoint.rsplit("/", 1)[0] + "/result"
            while data.get("status") != "succeeded":
                st = data.get("status")
                if st == "violation":
                    raise ImageError("画面描述被判违规，换个说法再试", retryable=False)
                if st == "failed" or r.status_code >= 400 and not st:
                    err = data.get("error") or data.get("msg") or f"HTTP {r.status_code}"
                    raise ImageError(f"生图失败：{err}", retryable="key" not in str(err).lower())
                if loop.time() > deadline:
                    raise ImageError("生图超时")
                await asyncio.sleep(4)
                try:
                    q = await c.post(result_url, headers=headers, json={"id": data.get("id")}, timeout=20)
                    d = q.json()
                    d = d.get("data") if isinstance(d.get("data"), dict) else d
                    if d.get("status"):
                        data = {**d, "id": d.get("id") or data.get("id")}
                except (httpx.HTTPError, ValueError):
                    pass
            results = data.get("results") or []
            first = results[0] if results else None
            url = first if isinstance(first, str) else ((first or {}).get("url") or (first or {}).get("imageUrl") or "")
            if not url:
                raise ImageError("生图接口没有返回图片")
            try:
                img = await c.get(url, timeout=60)
                img.raise_for_status()
            except httpx.HTTPError as e:
                raise ImageError(f"图片下载失败：{type(e).__name__}") from e
            return img.content


_provider_factory: Callable[[], ImageProvider] | None = None


def mold_slot(local: list[str], idx: int) -> int:
    """新图第 idx 张照着原帖第几张（0 起）：一张对一张；新图比原帖多时，多出来的轮流用原帖内页。"""
    if idx < len(local):
        return idx
    return 1 + (idx - 1) % (len(local) - 1) if len(local) > 1 else 0


def get_provider() -> ImageProvider:
    if _provider_factory is not None:
        return _provider_factory()
    return GrsaiProvider()


def set_provider_factory(f: Callable[[], ImageProvider] | None) -> None:
    global _provider_factory
    _provider_factory = f


async def _expand_set(llm: LLM, image_style: str, draft: Draft, images: list[DraftImage], targets: list[DraftImage],
                      molds: dict[int, int]) -> tuple[str, dict[int, str]]:
    """一次给整套图定统一视觉规范、写每张提示词：返回 (规范, {idx: 提示词})。已有规范时原样沿用。"""
    ref = draft.reference or {}
    fixed = (draft.image_spec or "").strip()
    try:
        data = await complete_json(llm, [
            {"role": "system", "content": prompts.IMAGE_SET_SYSTEM},
            {"role": "user", "content": prompts.IMAGE_SET_USER.format(
                image_style=image_style or "手机实拍的生活感，自然光", title=draft.title,
                spec_block=prompts.IMAGE_SPEC_FIXED.format(spec=fixed) if fixed else "",
                total=len(images),
                all="\n".join(f"第 {i.idx + 1} 张{'（封面）' if i.idx == 0 else ''}：{i.prompt}" for i in images),
                targets="、".join(f"第 {i.idx + 1} 张" for i in targets),
                mold_block=prompts.IMAGE_MOLD_BLOCK.format(
                    ref_title=str(ref.get("title", ""))[:30],
                    pairs="；".join(f"第 {i.idx + 1} 张照原帖第 {molds[i.idx] + 1} 张" for i in targets if i.idx in molds),
                ) if molds else "",
            )},
        ], temperature=0.5)
        spec = fixed or str(data.get("spec") or "").strip()
        got = {}
        for x in data.get("prompts") or []:
            try:
                got[int(x.get("idx")) - 1] = str(x.get("prompt") or "").strip()
            except (TypeError, ValueError, AttributeError):
                continue
    except (LLMError, TypeError, ValueError) as e:
        logger.warning("配图提示词扩写失败，用原始描述：%s", e)
        spec, got = fixed, {}
    spec = spec or f"整套图统一：{image_style or '手机实拍的生活感，自然光'}，同样的配色、字体和画面质感"
    return spec[:600], {i.idx: got.get(i.idx) or i.prompt for i in targets}


def _final_prompt(prompt: str, spec: str, *, mold: bool, anchor: int | None) -> str:
    """每张发给生图模型的提示词：先说附的参考图各是什么，再是这张的内容，最后是整套统一的规范。"""
    head = []
    if mold and anchor is not None:
        head.append(f"参考图 1 是版式模板：严格照着它的版式做一张新图；参考图 2 是同一套里已经出好的第 {anchor + 1} 张，"
                    "配色、字体、文字样式、人物和它保持一致。")
    elif mold:
        head.append("严格照着参考图的版式做一张新图（构图、文字位置和字号层级、装饰、分格都照它，内容和文字换成下面的）。")
    elif anchor is not None:
        head.append(f"参考图是同一套里已经出好的第 {anchor + 1} 张：新图的配色、字体、文字样式、背景质感、人物和它保持一致，"
                    "构图和内容按下面的来。")
    return "\n".join([*head, prompt, f"【这一套图统一的视觉规范，必须遵守】{spec}"])


async def generate_images(
    session: Session,
    llm: LLM,
    draft_id: str,
    *,
    only_idx: int | None = None,
    emit: Callable[[str, str, dict | None], None] = lambda *a: None,
) -> dict:
    draft = session.get(Draft, draft_id)
    if draft is None:
        raise LookupError("草稿不存在")
    account = session.get(Account, draft.account_id)
    q = select(DraftImage).where(DraftImage.draft_id == draft_id).order_by(col(DraftImage.idx))
    images = list(session.exec(q).all())
    targets = [i for i in images if (only_idx is None and i.status != ImageStatus.done) or i.idx == only_idx]
    if not image_configured():
        for i in targets:
            i.status = ImageStatus.skipped
            session.add(i)
        session.commit()
        emit("warning", "没有配置配图服务（AI 配图 API Key），跳过配图", None)
        return {"done": 0, "failed": 0, "skipped": len(targets)}

    try:
        provider = get_provider()
    except ImageError as e:
        for i in targets:
            i.status, i.error = ImageStatus.failed, str(e)
            session.add(i)
        session.commit()
        raise
    out_dir = get_settings().images_dir / draft_id
    out_dir.mkdir(parents=True, exist_ok=True)
    for img in targets:
        img.status, img.error, img.updated_at = ImageStatus.running, "", utcnow()
        session.add(img)
    session.commit()
    sem = asyncio.Semaphore(max(1, get_settings().image_concurrency))  # 几张一起出，6 张不用排队等
    ref = draft.reference or {}
    local = [p for p in ref.get("local") or [] if (get_settings().images_dir / p).exists()] if use_refs() else []
    molds = {i.idx: mold_slot(local, i.idx) for i in targets} if local else {}
    if local:
        emit("image", f"照着参考帖「{ref.get('title', '')[:20]}」的原图出图，一张对一张学版式，整套用同一份视觉规范", None)
    tset = {i.id for i in targets}
    done_others = [i for i in images if i.id not in tset and i.status == ImageStatus.done and i.path]
    if not done_others:
        draft.image_spec = ""  # 整套从头出：重新定规范
    style = account.image_style if account else ""
    spec, expanded = await _expand_set(llm, style, draft, images, targets, molds)
    draft.image_spec = spec
    session.add(draft)
    session.commit()
    counter = {"done": 0, "failed": 0}
    total = len(targets)
    anchor: dict[str, DraftImage | None] = {"img": None}
    if done_others:
        anchor["img"] = next((i for i in done_others if i.idx == 0), done_others[0])

    def progress() -> dict:
        return {"done": counter["done"], "failed": counter["failed"], "total": total}

    def anchor_uri() -> tuple[int | None, str | None]:
        a = anchor["img"]
        if a is None or not a.path:
            return None, None
        path = get_settings().images_dir / a.path
        return (a.idx, uri_of(path.read_bytes())) if path.exists() else (None, None)

    async def one(img: DraftImage) -> None:
        async with sem:
            emit("image", f"第 {img.idx + 1} 张出图中…", {"idx": img.idx, **progress()})
            try:
                mold_uri = None
                if img.idx in molds:
                    img.ref_path = local[molds[img.idx]]
                    mold_uri = local_uri(img.ref_path)
                a_idx, a_uri = anchor_uri() if anchor["img"] is not img else (None, None)
                r = [u for u in (mold_uri, a_uri) if u]
                img.expanded_prompt = _final_prompt(expanded[img.idx], spec, mold=bool(mold_uri),
                                                    anchor=a_idx if a_uri else None)
                try:
                    data = await provider.generate(img.expanded_prompt, r or None)
                except ImageError as e:
                    if not r or not e.retryable:
                        raise
                    logger.warning("带参考图出图失败（%s），不带参考图再试", e)
                    data = await provider.generate(_final_prompt(expanded[img.idx], spec, mold=False, anchor=None))
                name = f"{img.idx:02d}-{uuid4().hex[:8]}.png"
                (out_dir / name).write_bytes(data)
                img.path, img.status = f"{draft_id}/{name}", ImageStatus.done
                counter["done"] += 1
                emit("image", f"第 {img.idx + 1} 张好了", {"idx": img.idx, **progress()})
            except Exception as e:  # noqa: BLE001 - 单张失败不影响其他张
                img.status, img.error = ImageStatus.failed, str(e)[:300]
                counter["failed"] += 1
                emit("warning", f"第 {img.idx + 1} 张配图失败：{e}", {"idx": img.idx, **progress()})
            img.updated_at = utcnow()
            session.add(img)
            session.commit()

    first: list[DraftImage] = []
    if anchor["img"] is None and not molds and len(targets) > 1:
        # 没有参考帖、从头出一整套：先出封面，其余带上它当风格参照，免得每张各是各的样子
        first = [targets[0]]
        emit("image", "先出封面，其余几张照着封面的配色和字体出，保证一套统一", None)
    try:
        if first:
            await one(first[0])
            if first[0].status == ImageStatus.done:
                anchor["img"] = first[0]
        await asyncio.gather(*(one(i) for i in targets if i not in first))
    finally:  # 任务被取消/出意外时，别把图留在「生成中」
        left = [i for i in targets if i.status in (ImageStatus.pending, ImageStatus.running)]
        for i in left:
            i.status, i.error = ImageStatus.failed, i.error or "没出完，点重新生成"
            session.add(i)
        if left:
            session.commit()
    return {**counter, "skipped": 0}
