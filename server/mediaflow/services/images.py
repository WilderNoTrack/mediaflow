"""AI 配图：一整套中文画面描述 → 一次扩写成「统一视觉规范 + 每张提示词」→ 生图服务 → 存到本地 data/images。

一套图必须统一：
- 规范存在 draft.image_spec，每张的提示词都带上同一份；只重出某几张时沿用，不重新定
- 有参考帖原图时，每张照着同一篇参考帖里对应的那张做版式（不会混用好几篇帖子的图）
- 已经有出好的图时（重出某张、补出失败的），把同套里出好的一张也带上当风格参照；
  没有参考帖、要从头出一整套时，先出封面，其余几张带上封面一起出

生图服务抽象成 ImageProvider，有两条通道，模型都是界面里选的那个（GPT Image 2.5 / Nano Banana）：
- openai-next（填了 Key 就优先用）：OpenAI 兼容的 /images/generations，同步返回
- grsai（备用）：openai-next 额度用完或出不了图时自动换它；额度用完会记下来，之后几个小时直接走 grsai
要换别家，实现一个 generate(prompt, refs) -> bytes 即可。
"""

from __future__ import annotations

import asyncio
import base64
import logging
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import uuid4

import httpx
from sqlmodel import Session, col, select

from mediaflow import credentials
from mediaflow.agents import prompts
from mediaflow.config import Settings, get_settings
from mediaflow.domain.models import Account, Draft, DraftImage, ImageStatus, utcnow
from mediaflow.llm.client import LLM, LLMError, complete_json, get_vision_llm
from mediaflow.services import layout as layout_mod
from mediaflow.services import visual as visual_mod
from mediaflow.services import webimg
from mediaflow.services.refs import local_uri, uri_of

logger = logging.getLogger(__name__)


class ImageError(RuntimeError):
    def __init__(self, msg: str, *, retryable: bool = True, exhausted: bool = False) -> None:
        super().__init__(msg)
        self.retryable = retryable  # 违规/密钥错误换模型也没用
        self.exhausted = exhausted  # 额度用完了（换通道）


@dataclass(frozen=True)
class ImageModel:
    id: str
    label: str
    desc: str
    payload: dict


# 都是 grsai 节点上的模型，同一个 Key；都出 3:4 竖图（小红书标准比例）
MODELS: list[ImageModel] = [
    ImageModel("gpt-image-2.5", "GPT Image 2.5",
               "推荐。更像小红书封面：大字标题排版好看、画面有设计感", {"aspectRatio": "3:4"}),
    ImageModel("nano-banana-2.1", "Nano Banana 2.1",
               "出图快，画面更写实像实拍（openai-next 上用的是 Gemini 3.1 Flash Image）", {"aspectRatio": "3:4", "imageSize": "1K"}),
]
_MODELS = {m.id: m for m in MODELS}


def image_key() -> str:
    return credentials.get("image_api_key")


def next_key() -> str:
    return credentials.get("image_next_api_key")


NEXT_PAUSE_HOURS = 6  # openai-next 额度用完后这么久内直接走 grsai，过了再试（可能充值了）


def next_exhausted_at() -> str:
    """openai-next 额度用完的时间（ISO），没用完 / 已经过了暂停期返回空。"""
    at = credentials.get("image_next_exhausted")
    if not at:
        return ""
    try:
        t = datetime.fromisoformat(at)
    except ValueError:
        return ""
    return at if datetime.now(UTC) - t < timedelta(hours=NEXT_PAUSE_HOURS) else ""


def mark_next_exhausted(on: bool = True) -> None:
    credentials.update({"image_next_exhausted": datetime.now(UTC).isoformat() if on else ""})


def active_channel() -> str:
    """现在实际先用哪条：next / grsai / 空（都没配）。"""
    if next_key() and (not next_exhausted_at() or not image_key()):
        return "next"
    return "grsai" if image_key() else ""


def channels() -> list[str]:
    """出图按顺序走哪几条通道（openai-next 额度用完的暂停期内，ChainProvider 会跳过它）。"""
    out = ["next"] if next_key() else []
    if image_key():
        out.append("grsai")
    return out


def image_model() -> str:
    return credentials.get("image_model") or get_settings().image_model


def image_configured() -> bool:
    return bool(image_key() or next_key())


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


# 界面里的模型 → openai-next 上对应的模型和出 3:4 竖图的参数
NEXT_MODELS: dict[str, tuple[str, dict]] = {
    "gpt-image-2.5": ("gpt-image-2.5", {"size": "1152x1536"}),
    "nano-banana-2.1": ("gemini-3.1-flash-image", {"aspect_ratio": "3:4"}),
}
_QUOTA_WORDS = ("quota", "额度", "余额", "insufficient", "balance", "credit", "用尽", "欠费", "充值", "recharge")


class OpenAINextProvider:
    """openai-next 生图：POST /images/generations（同步出图，参考图放 image 数组里传 data URL）。
    主模型失败自动换另一个模型重试一次；额度用完直接报 exhausted，让外面换 grsai。"""

    def __init__(self, settings: Settings | None = None, *, model: str | None = None, key: str | None = None,
                 fallback: bool = True) -> None:
        self.s = settings or get_settings()
        self.key = key if key is not None else next_key()
        if not self.key:
            raise ImageError("没有配置 openai-next 的 API Key", retryable=False)
        self.model = model or image_model()
        others = [m for m in NEXT_MODELS if m != self.model]
        self.fallback = others[0] if fallback and others else None

    async def generate(self, prompt: str, refs: list[str] | None = None) -> bytes:
        try:
            return await self._one(self.model, prompt, refs)
        except ImageError as e:
            if not self.fallback or not e.retryable or e.exhausted:
                raise
            logger.warning("openai-next %s 生图失败（%s），换 %s 再试", self.model, e, self.fallback)
            return await self._one(self.fallback, prompt, refs)

    async def _one(self, model: str, prompt: str, refs: list[str] | None = None) -> bytes:
        real, extra = NEXT_MODELS.get(model, (model, {"size": "1152x1536"}))
        # 平台会拦默认 UA，按它的文档用 curl 的
        headers = {"Authorization": f"Bearer {self.key}", "User-Agent": "curl/8.5.0"}
        body = {"model": real, "prompt": prompt, "n": 1, **extra, **({"image": refs} if refs else {})}
        url = self.s.image_next_base_url.rstrip("/") + "/images/generations"
        async with httpx.AsyncClient(timeout=httpx.Timeout(self.s.image_timeout, connect=15)) as c:
            try:
                r = await c.post(url, headers=headers, json=body)
            except httpx.HTTPError as e:
                raise ImageError(f"连不上 openai-next：{type(e).__name__}") from e
            try:
                data = r.json()
            except ValueError:
                raise ImageError(f"openai-next HTTP {r.status_code}：{r.text[:200]}") from None
            items = data.get("data") if isinstance(data, dict) else None
            if r.status_code >= 400 or not items:
                err = data.get("error") if isinstance(data, dict) else None
                msg = str((err or {}).get("message") if isinstance(err, dict) else err or data.get("message") or "")[:200]
                low = msg.lower()
                if r.status_code == 402 or any(w in low for w in _QUOTA_WORDS):
                    raise ImageError(f"openai-next 额度用完了：{msg or r.status_code}", retryable=False, exhausted=True)
                if r.status_code == 401 or "invalid token" in low:
                    raise ImageError("openai-next 的 API Key 不对或已失效", retryable=False)
                if any(w in low for w in ("safety", "moderation", "content policy", "违规", "敏感")):
                    raise ImageError("画面描述被判违规，换个说法再试", retryable=False)
                raise ImageError(f"openai-next 生图失败：{msg or f'HTTP {r.status_code}'}")
            first = items[0] if isinstance(items[0], dict) else {}
            if first.get("b64_json"):
                try:
                    return base64.b64decode(first["b64_json"])
                except ValueError as e:
                    raise ImageError("openai-next 返回的图片解不开") from e
            if not first.get("url"):
                raise ImageError("openai-next 没有返回图片")
            try:
                img = await c.get(first["url"], timeout=60)
                img.raise_for_status()
            except httpx.HTTPError as e:
                raise ImageError(f"图片下载失败：{type(e).__name__}") from e
            return img.content


class ChainProvider:
    """按顺序试几条通道：openai-next → grsai。openai-next 额度用完记下来，暂停期内直接走 grsai。"""

    def __init__(self, providers: list[tuple[str, ImageProvider]]) -> None:
        if not providers:
            raise ImageError("没有配置配图 API Key", retryable=False)
        self.providers = providers

    async def generate(self, prompt: str, refs: list[str] | None = None) -> bytes:
        last: ImageError | None = None
        for i, (name, p) in enumerate(self.providers):
            if name == "next" and len(self.providers) > 1 and next_exhausted_at():
                continue  # 额度用完的暂停期内直接走 grsai
            try:
                data = await p.generate(prompt, refs)
            except ImageError as e:
                last = e
                if name == "next" and e.exhausted:
                    if not next_exhausted_at():
                        logger.warning("openai-next 额度用完了，接下来先用 grsai（%s 小时后再试 openai-next）", NEXT_PAUSE_HOURS)
                    mark_next_exhausted()
                if i + 1 < len(self.providers):
                    logger.warning("%s 没出来（%s），换 %s", _CHANNEL_LABEL[name], e, _CHANNEL_LABEL[self.providers[i + 1][0]])
                continue
            if name == "next" and next_exhausted_at():
                mark_next_exhausted(False)  # 又能出了（充值了）
            return data
        assert last is not None
        raise last


_CHANNEL_LABEL = {"next": "openai-next", "grsai": "grsai"}


def channel_provider(name: str, *, key: str | None = None, model: str | None = None, fallback: bool = True) -> ImageProvider:
    if name == "next":
        return OpenAINextProvider(key=key, model=model, fallback=fallback)
    return GrsaiProvider(key=key, model=model, fallback=fallback)


_provider_factory: Callable[[], ImageProvider] | None = None


def mold_slot(local: list[str], idx: int) -> int:
    """新图第 idx 张照着原帖第几张（0 起）：一张对一张；新图比原帖多时，多出来的轮流用原帖内页。"""
    if idx < len(local):
        return idx
    return 1 + (idx - 1) % (len(local) - 1) if len(local) > 1 else 0


def get_provider() -> ImageProvider:
    if _provider_factory is not None:
        return _provider_factory()
    return ChainProvider([(c, channel_provider(c)) for c in channels()])


def set_provider_factory(f: Callable[[], ImageProvider] | None) -> None:
    global _provider_factory
    _provider_factory = f


# ─── 配图做法：不止 AI 画 ────────────────────────────────────────────────────────
# 账号设定（account.image_mode）：整个账号默认怎么出图
ACCOUNT_MODES: dict[str, str] = {
    "ai": "AI 画整张图",
    "mixed": "AI 画画面，字用代码排",
    "card": "代码排版的文字卡片",
    "photo": "网上找真实图片 + 代码排字",
    "auto": "每张自动挑最合适的做法",
}
# 每张图实际的做法（draft_image.mode 用户指定 / made_by 实际做法）
IMAGE_MODES = ("ai", "ai_text", "card", "photo")
MODE_LABEL = {"ai": "AI 画", "ai_text": "AI 画面 + 代码排字", "card": "排版卡片", "photo": "网上找图 + 排字"}
_CHOICES = {"ai": ["ai"], "mixed": ["ai_text", "card"], "card": ["card"], "photo": ["photo", "card"],
            "auto": ["ai_text", "card", "photo", "ai"]}
_NEEDS_AI = ("ai", "ai_text")
_DOING = {"ai": "出图中", "ai_text": "AI 画画面中", "card": "排版中", "photo": "去网上找图"}
LAYOUT_KEYS = ("kind", "title", "subtitle", "tag", "items", "left", "right", "highlight", "position", "footer", "palette")


# 照参考帖出图：原图是哪种做法，这张优先用哪几种（和账号允许的取交集；用户单独指定了做法的不管）
LOOK_MODES = {"photo": ["photo", "ai"], "photo_text": ["ai_text", "ai", "photo"], "collage": ["ai"],
              "illustration": ["ai"], "text_note": ["ai", "card"], "card": ["card", "ai_text"], "screenshot": ["ai", "card"]}


def look_options(opts: list[str], page: dict | None) -> list[str]:
    want = LOOK_MODES.get(str((page or {}).get("kind") or ""), [])
    picked = [m for m in want if m in opts]
    return picked or opts


def account_mode(account: Account | None) -> str:
    m = (getattr(account, "image_mode", "") or "ai") if account else "ai"
    return m if m in ACCOUNT_MODES else "ai"


def mode_options(img_mode: str, acc_mode: str, has_ai: bool) -> list[str]:
    """这张图能用哪几种做法（第一个是默认）。没配 AI 配图时去掉要 AI 的；账号就是「AI 画」又没配 Key 时返回空（跳过）。"""
    opts = [img_mode] if img_mode in IMAGE_MODES else list(_CHOICES.get(acc_mode, ["ai"]))
    if not has_ai:
        opts = [m for m in opts if m not in _NEEDS_AI]
        if not opts and not img_mode and acc_mode != "ai":
            opts = ["card"]
    return opts


def can_make(account: Account | None) -> bool:
    """写完稿能不能直接出图：配了 AI 配图，或者账号设的做法不用 AI（排版卡片 / 网上找图）。"""
    return image_configured() or account_mode(account) != "ai"


def _strs(v, n: int = 8, size: int = 60) -> list[str]:
    if isinstance(v, str):
        v = [x for x in re.split(r"\n|；|;", v)]
    if not isinstance(v, list):
        return []
    return [" ".join(str(x).split())[:size] for x in v if str(x).strip()][:n]


def clean_layout(raw: dict | None) -> dict:
    """模型/用户给的 layout 只留认识的字段。"""
    raw = raw if isinstance(raw, dict) else {}
    out: dict = {}
    kind = str(raw.get("kind") or "").strip().lower()
    if kind == "none":  # 照着没字的原图：这张不排字
        pal = str(raw.get("palette") or "").lower()
        return {"kind": "none", **({"palette": pal} if pal in layout_mod.PALETTES else {})}
    out["kind"] = kind if kind in layout_mod.KINDS else "cover"
    for k in ("title", "subtitle", "tag", "highlight", "footer"):
        if str(raw.get(k) or "").strip():
            out[k] = " ".join(str(raw[k]).split())[:90]
    items = _strs(raw.get("items"))
    if items:
        out["items"] = items
    for side in ("left", "right"):
        c = raw.get(side)
        if isinstance(c, dict) and (c.get("title") or c.get("items")):
            out[side] = {"title": " ".join(str(c.get("title") or "").split())[:12], "items": _strs(c.get("items"), 6)}
    pos = str(raw.get("position") or "").lower()
    if pos in ("top", "center", "bottom"):
        out["position"] = pos
    pal = str(raw.get("palette") or "").lower()
    if pal in layout_mod.PALETTES:
        out["palette"] = pal
    if out["kind"] == "compare" and not (out.get("left") or out.get("right")):
        out["kind"] = "list" if items else "cover"
    if out["kind"] in ("list", "steps") and not items:
        out["kind"] = "cover"
    return out


def _fallback_layout(img: DraftImage, draft: Draft) -> dict:
    """模型没给 layout 时，从描述里「」括起来的字凑一份：第一处当标题，其余当要点；封面用笔记标题。"""
    quoted = [q.strip() for q in re.findall(r"「([^」]{1,40})」", img.prompt or "") if q.strip()]
    if img.idx == 0:
        lay = {"kind": "cover", "title": quoted[0] if quoted else draft.title}
        if len(quoted) >= 2:
            lay["subtitle"] = " · ".join(quoted[1:4])
        return lay
    if len(quoted) >= 3:
        return {"kind": "list", "title": quoted[0], "items": quoted[1:7]}
    head = re.split(r"[，。,；;：:]", re.sub(r"^[^：:]{0,6}[：:]", "", img.prompt or ""))[0]
    return {"kind": "cover", "title": quoted[0] if quoted else head[:20] or draft.title}


async def _expand_set(llm: LLM, image_style: str, draft: Draft, images: list[DraftImage], targets: list[DraftImage],
                      molds: dict[int, int], template: dict | None = None,
                      opts: dict[int, list[str]] | None = None, ex_hint: str = "") -> tuple[str, dict[int, dict], str]:
    """一次给整套图定统一视觉规范、写每张的做法：返回 (规范, {idx: {prompt, type, mode, layout, query}}, 配色)。
    已有规范时原样沿用。有账号配图模板时，规范照模板的整体视觉，每张再选一种页型。
    opts 是每张能用的做法；全是「AI 画」时和原来一样只写提示词。"""
    ref = draft.reference or {}
    fixed = (draft.image_spec or "").strip()
    opts = opts or {}
    mixed = any(o != ["ai"] for o in opts.values())
    used = sorted({m for o in opts.values() for m in o}, key=IMAGE_MODES.index)
    modes_block = prompts.IMAGE_MODES_BLOCK.format(
        options="\n".join(prompts.IMAGE_MODE_OPTIONS[m] for m in used),
        allowed="；".join(f"第 {i.idx + 1} 张 {' / '.join(opts.get(i.idx) or ['ai'])}" for i in targets),
        palettes="、".join(f"{k}（{v['label']}）" for k, v in layout_mod.PALETTES.items()),
    ) if mixed else ""
    plans: dict[int, dict] = {}
    pal = ""
    try:
        data = await complete_json(llm, [
            {"role": "system", "content": prompts.IMAGE_SET_SYSTEM},
            {"role": "user", "content": prompts.IMAGE_SET_USER.format(
                image_style=image_style or "手机实拍的生活感，自然光", title=draft.title,
                spec_block=prompts.IMAGE_SPEC_FIXED.format(spec=fixed) if fixed else "",
                total=len(images),
                all="\n".join(f"第 {i.idx + 1} 张{'（封面）' if i.idx == 0 else ''}：{i.prompt}" for i in images),
                targets="、".join(f"第 {i.idx + 1} 张" for i in targets),
                mold_block=(prompts.EXEMPLAR_MOLD_BLOCK if ref.get("source") == "exemplar" else prompts.IMAGE_MOLD_BLOCK).format(
                    ref_title=str(ref.get("title", ""))[:30],
                    pairs="；".join(f"第 {i.idx + 1} 张照{'样板' if ref.get('source') == 'exemplar' else '原帖'}第 {molds[i.idx] + 1} 张"
                                   for i in targets if i.idx in molds),
                ) + _look_block(ref, molds, targets) + ex_hint if molds else ex_hint,
                template_block=visual_mod.template_block(template) if template else "",
                type_field=', "type": "页型"' if template else "",
                modes_block=modes_block,
                palette_field=', "palette": "配色名"' if mixed else "",
                mode_fields=', "mode": "做法", "layout": {…}, "query": ["搜图关键词"]' if mixed else "",
            )},
        ], temperature=0.5)
        spec = fixed or str(data.get("spec") or "").strip()
        pal = str(data.get("palette") or "").strip().lower()
        for x in data.get("prompts") or []:
            if not isinstance(x, dict):
                continue
            try:
                k = int(x.get("idx")) - 1
            except (TypeError, ValueError):
                continue
            plans[k] = {"prompt": str(x.get("prompt") or "").strip(), "type": str(x.get("type") or "").strip(),
                        "mode": str(x.get("mode") or "").strip().lower(),
                        "layout": x.get("layout") if isinstance(x.get("layout"), dict) else {},
                        "query": _strs(x.get("query"), 3, 30)}
    except (LLMError, TypeError, ValueError, AttributeError) as e:
        logger.warning("配图提示词扩写失败，用原始描述：%s", e)
        spec, plans = fixed, {}
    if template and not spec:
        spec = str(template.get("spec") or "")
    spec = spec or f"整套图统一：{image_style or '手机实拍的生活感，自然光'}，同样的配色、字体和画面质感"
    out = {}
    for i in targets:
        p = plans.get(i.idx) or {}
        out[i.idx] = {"mode": "", "layout": {}, "query": [], **p, "prompt": p.get("prompt") or i.prompt, "type": p.get("type", "")}
    return spec[:600], out, pal if pal in layout_mod.PALETTES else ""


def _look_pages(ref: dict) -> list[dict]:
    if ref.get("source") == "exemplar":
        return []
    return [p for p in ((ref.get("look") or {}).get("pages") or []) if isinstance(p, dict)]


def _look_block(ref: dict, molds: dict[int, int], targets: list[DraftImage]) -> str:
    """看图模型读过原帖的图：把每张原图的做法写给出图的模型（它自己看不到图）。"""
    pages = _look_pages(ref)
    if not pages:
        return ""
    rows = [f"第 {i.idx + 1} 张对应的原图（第 {molds[i.idx] + 1} 张）：{visual_mod.look_line(pages[molds[i.idx]])}"
            for i in targets if i.idx in molds and molds[i.idx] < len(pages) and visual_mod.look_line(pages[molds[i.idx]])]
    if not rows:
        return ""
    return prompts.IMAGE_LOOK_BLOCK.format(spec=(ref.get("look") or {}).get("spec") or "（没读出来，按每张原图的做法）",
                                           pages="\n".join(rows))


def _final_prompt(prompt: str, spec: str, *, mold: bool, anchor: int | None, no_text: bool = False) -> str:
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
    tail = ["【这张画面里不要出现任何文字、数字、字母和 logo，参考图里的字也不要照搬；也不要画空白的标签、便签、文字框、"
            "占位方块。文字之后会用代码排上去，按描述在那一侧留出干净的背景（桌面、墙面、天空这类）】"] if no_text else []
    return "\n".join([*head, prompt, f"【这一套图统一的视觉规范，必须遵守】{spec}", *tail])


def rerender(img: DraftImage, changes: dict) -> None:
    """改代码排上去的字：合并改动，按原来的底图重新排一遍（不重新生图、不花额度）。改不了抛 LayoutError。"""
    if img.made_by not in ("card", "photo", "ai_text") or img.status != ImageStatus.done:
        raise layout_mod.LayoutError(f"第 {img.idx + 1} 张的字是 AI 直接画在画面里的，没法直接改字；"
                                     "把这张换成「AI 画面 + 代码排字」或「排版卡片」重出一次，以后就能直接改")
    merged = {**(img.layout or {}), **{k: v for k, v in (changes or {}).items() if k in LAYOUT_KEYS and v is not None}}
    if merged.get("kind") == "none" and any(merged.get(k) for k in ("title", "subtitle", "tag", "items")):
        merged["kind"] = "list" if merged.get("items") else "cover"  # 原来没字的图要加字：按封面 / 清单排
    lay = clean_layout(merged)
    images_dir = get_settings().images_dir
    base = None
    if img.made_by != "card":
        rel = str((img.source or {}).get("base") or "")
        if not rel or not (images_dir / rel).exists():
            raise layout_mod.LayoutError(f"第 {img.idx + 1} 张的底图找不到了，重出这张再改字")
        base = (images_dir / rel).read_bytes()
    data = layout_mod.render(img.made_by, lay, base, lay.get("palette"))
    out_dir = images_dir / img.draft_id
    out_dir.mkdir(parents=True, exist_ok=True)
    name = f"{img.idx:02d}-{uuid4().hex[:8]}.png"
    (out_dir / name).write_bytes(data)
    img.path, img.layout, img.updated_at = f"{img.draft_id}/{name}", lay, utcnow()


def _exemplar_slots(ref: dict, targets: list[DraftImage]) -> tuple[list[str], list[dict], dict[int, int]]:
    """照样板帖出图时：(样板每张的版式模板图, 样板每张的做法/版式/配色, 这篇第几张对样板第几张)。不是样板帖返回空。"""
    if ref.get("source") != "exemplar":
        return [], [], {}
    images_dir = get_settings().images_dir
    pairs = [(p, pl) for p, pl in zip(ref.get("local") or [], ref.get("plan") or []) if p and (images_dir / p).exists()]
    local, plan = [p for p, _ in pairs], [pl for _, pl in pairs]
    return local, plan, ({i.idx: mold_slot(local, i.idx) for i in targets} if local else {})


def _exemplar_hint(plan: list[dict], slot: dict[int, int], targets: list[DraftImage]) -> str:
    rows = []
    for i in targets:
        if i.idx not in slot:
            continue
        p = plan[slot[i.idx]]
        kind = f"，layout.kind 用 {p['kind']}" if p.get("kind") else ""
        how = f"（这张的原型：{p['look']}）" if p.get("look") else ""
        rows.append(f"第 {i.idx + 1} 张照样板第 {slot[i.idx] + 1} 张：{MODE_LABEL.get(p.get('made_by') or 'ai', 'AI 画')}{kind}{how}")
    return ("\n【照样板帖做】每张的做法和版式跟样板对应那张一样，信息量也相当，只换内容和字：" + "；".join(rows)) if rows else ""


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
    has_ai = image_configured()
    acc_mode = account_mode(account)
    opts = {i.idx: mode_options(i.mode, acc_mode, has_ai) for i in targets}
    ref = draft.reference or {}
    if ref.get("source") == "exemplar":
        from mediaflow.services import exemplar

        fresh = exemplar.refresh(session, ref)
        if fresh != ref:  # 存回去：草稿页的「照着样板帖第 N 张」也跟着对上
            draft.reference = ref = fresh
            session.add(draft)
            session.commit()
    ex_local, ex_plan, ex_slot = _exemplar_slots(ref, targets)
    # 账号有配图模板、参考帖又不是用户指定的：版式照模板，不按原图挑做法
    look = _look_pages(ref) if not (visual_mod.has_template(account) and ref.get("source") != "user") else []
    if look:  # 照参考帖：按看图模型读的原图做法挑（漫画、拼图让 AI 画整张，没字的实拍不排字…）
        n_local = len(ref.get("local") or [])
        for i in targets:
            if not i.mode and n_local:
                k = mold_slot(ref.get("local") or [], i.idx)
                opts[i.idx] = look_options(opts[i.idx], look[k] if k < len(look) else None)
    for i in targets:  # 照样板帖：每张的做法跟样板对应那张一样（账号设定允许、用户没单独指定时）
        want = ex_plan[ex_slot[i.idx]].get("made_by") if i.idx in ex_slot and not i.mode else None
        if want in opts[i.idx]:
            opts[i.idx] = [want]
    skip = [i for i in targets if not opts[i.idx]]
    if skip:
        for i in skip:
            i.status = ImageStatus.skipped
            i.error = "没有配置 AI 配图，这张换成「排版卡片」或「网上找图」就能出" if i.mode in _NEEDS_AI else ""
            session.add(i)
        session.commit()
        emit("warning", "没有配置配图服务（AI 配图 API Key），跳过配图" if len(skip) == len(targets)
             else f"没有配置 AI 配图，跳过 {len(skip)} 张要 AI 画的", None)
        if len(skip) == len(targets):
            return {"done": 0, "failed": 0, "skipped": len(targets)}
        targets = [i for i in targets if opts[i.idx]]
    ai_targets = [i for i in targets if set(opts[i.idx]) & set(_NEEDS_AI)]

    provider: ImageProvider | None = None
    if ai_targets:
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
    if ex_local:
        local = ex_local if use_refs() and ai_targets else []
    else:
        local = [p for p in ref.get("local") or [] if (get_settings().images_dir / p).exists()] if use_refs() and ai_targets else []
    # 版式照什么：样板帖 > 用户自己给的参考帖 > 账号配图模板 > 自动挑的参考帖（只管 AI 画的那几张）
    tpl = account.visual if ai_targets and visual_mod.has_template(account) and not ex_local \
        and not (local and ref.get("source") == "user") else None
    slots = {i.idx: mold_slot(local, i.idx) for i in ai_targets} if local and not tpl else {}
    if tpl:
        draft.image_mold = "template"
        emit("image", "照着账号的配图模板出图：每张选一种页型、照它的样例做版式，整个账号统一一个风格", None)
    elif ex_local:
        draft.image_mold = "post"
        emit("image", f"照着样板帖「{ref.get('title', '')[:20]}」出图：一张对一张照它的做法、版式和配色", None)
    elif slots:
        draft.image_mold = "post"
        emit("image", f"照着参考帖「{ref.get('title', '')[:20]}」的原图出图，一张对一张学版式，整套用同一份视觉规范", None)
    else:
        draft.image_mold = ""
    if ex_slot:  # 照样板帖时每张的做法已经定了，不再说账号默认做法
        cnt = Counter(MODE_LABEL.get(opts[i.idx][0], "自动") if len(opts[i.idx]) == 1 else "自动挑" for i in targets)
        emit("image", "这套图的做法照样板帖：" + "、".join(f"{k} {n} 张" for k, n in cnt.items()), None)
    elif acc_mode != "ai" or any(i.mode for i in targets):
        emit("image", "这套图的做法：" + "；".join(sorted({ACCOUNT_MODES[acc_mode]} | {MODE_LABEL[i.mode] for i in targets if i.mode})), None)
    tset = {i.id for i in targets}
    done_others = [i for i in images if i.id not in tset and i.status == ImageStatus.done and i.path]
    if not done_others:
        draft.image_spec = str(ref.get("image_spec") or "") if ex_plan else ""  # 整套从头出：重新定规范（照样板帖就用它的）
    style = account.image_style if account else ""
    spec, plans, pal = await _expand_set(llm, style, draft, images, targets, slots, tpl, opts,
                                         ex_hint=_exemplar_hint(ex_plan, ex_slot, targets))
    draft.image_spec = spec
    session.add(draft)
    # 配色整套一个：同套已出好的图用的 > 样板帖用的 > 模型这次选的 > 默认
    pal = next((str(i.layout.get("palette")) for i in done_others if (i.layout or {}).get("palette") in layout_mod.PALETTES), "") \
        or next((str(p["palette"]) for p in ex_plan if p.get("palette") in layout_mod.PALETTES), "") \
        or pal or layout_mod.DEFAULT_PALETTE
    final: dict[int, str] = {}
    for img in targets:
        o, m = opts[img.idx], plans[img.idx].get("mode")
        final[img.idx] = m if m in o else o[0]
        if final[img.idx] != "ai":
            lay = clean_layout(plans[img.idx].get("layout"))
            if lay.get("kind") == "none" and final[img.idx] in ("ai_text", "photo"):
                img.layout = {"kind": "none", "palette": pal}  # 原图没字：只要画面
                continue
            if not (lay.get("title") or lay.get("items") or lay.get("left")):
                lay = clean_layout(_fallback_layout(img, draft))
            if img.idx in ex_slot:  # 模型没说版式、文字位置的，照样板对应那张
                same, said = ex_plan[ex_slot[img.idx]], plans[img.idx].get("layout") or {}
                lay = clean_layout({**lay, **{k: same[k] for k in ("kind", "position") if same.get(k) and not said.get(k)}})
            img.layout = {**lay, "palette": pal}
    molds: dict[int, str] = {k: local[v] for k, v in slots.items() if final.get(k) in _NEEDS_AI}  # idx → 照着做版式的那张图
    for img in targets:
        if final[img.idx] not in _NEEDS_AI:
            img.page_type, img.ref_path = "", ""
        elif tpl:
            page = visual_mod.page_for(tpl, plans[img.idx].get("type") or img.page_type, img.idx)
            img.page_type = page["type"] if page else ""
            ex = visual_mod.example_of(page) if use_refs() else ""
            if ex:
                molds[img.idx] = ex
        session.add(img)
    session.commit()
    vllm = get_vision_llm("low") if visual_mod.check_enabled() else None
    pick_llm = get_vision_llm("low") if any(final[i.idx] == "photo" for i in targets) else None
    used_urls = {str((i.source or {}).get("url")) for i in images if i.id not in tset and (i.source or {}).get("url")}
    counter = {"done": 0, "failed": 0}
    total = len(targets)
    anchor: dict[str, DraftImage | None] = {"img": None}
    ai_done = [i for i in done_others if i.made_by in ("", "ai")]  # 只拿 AI 画的当风格参照（排了字的会让 AI 跟着写字）
    if ai_done:
        anchor["img"] = next((i for i in ai_done if i.idx == 0), ai_done[0])

    def progress() -> dict:
        return {"done": counter["done"], "failed": counter["failed"], "total": total}

    def anchor_uri() -> tuple[int | None, str | None]:
        a = anchor["img"]
        if a is None or not a.path:
            return None, None
        path = get_settings().images_dir / a.path
        return (a.idx, uri_of(path.read_bytes())) if path.exists() else (None, None)

    def save(data: bytes, img: DraftImage, suffix: str) -> str:
        name = f"{img.idx:02d}-{uuid4().hex[:8]}{suffix}"
        (out_dir / name).write_bytes(data)
        return f"{draft_id}/{name}"

    async def photo(img: DraftImage) -> bytes:
        queries = plans[img.idx].get("query") or [img.prompt[:24]]
        try:
            base, src = await webimg.find_photo(queries, img.prompt, vllm=pick_llm, avoid=used_urls)
        except webimg.WebImageError as e:
            emit("warning", f"第 {img.idx + 1} 张{e}，先做成排版卡片", {"idx": img.idx, **progress()})
            final[img.idx] = "card"
            img.source = {"fallback": str(e)[:120]}
            return await asyncio.to_thread(layout_mod.card, img.layout, pal)
        used_urls.add(src["url"])
        img.source = {**src, "base": save(base, img, "-base.jpg")}
        return await asyncio.to_thread(layout_mod.overlay, base, img.layout, pal)

    async def one(img: DraftImage) -> None:
        async with sem:
            mode = final[img.idx]
            emit("image", f"第 {img.idx + 1} 张{_DOING[mode]}…", {"idx": img.idx, **progress()})
            try:
                img.review = {}
                if mode == "card":
                    img.source, img.expanded_prompt = {}, ""
                    data = await asyncio.to_thread(layout_mod.card, img.layout, pal)
                elif mode == "photo":
                    img.expanded_prompt = ""
                    data = await photo(img)
                else:
                    assert provider is not None
                    img.ref_path = molds.get(img.idx, "")
                    mold_uri = local_uri(img.ref_path) if img.ref_path else None
                    a_idx, a_uri = anchor_uri() if anchor["img"] is not img else (None, None)
                    r = [u for u in (mold_uri, a_uri) if u]
                    no_text = mode == "ai_text"
                    prompt = plans[img.idx]["prompt"]
                    img.expanded_prompt = _final_prompt(prompt, spec, mold=bool(mold_uri), anchor=a_idx if a_uri else None,
                                                        no_text=no_text)

                    async def gen(p: str) -> bytes:
                        try:
                            return await provider.generate(p, r or None)
                        except ImageError as e:
                            if not r or not e.retryable:
                                raise
                            logger.warning("带参考图出图失败（%s），不带参考图再试", e)
                            return await provider.generate(_final_prompt(prompt, spec, mold=False, anchor=None, no_text=no_text))

                    data = await gen(img.expanded_prompt)
                    if no_text:
                        img.source = {"base": save(data, img, "-base.png")}
                        data = await asyncio.to_thread(layout_mod.overlay, data, img.layout, pal)
                    else:
                        img.source, img.layout = {}, {}
                        if vllm is not None:
                            data = await _review(img, data, gen, r)
                img.path, img.status = save(data, img, ".png"), ImageStatus.done
                img.made_by = final[img.idx]
                counter["done"] += 1
                emit("image", f"第 {img.idx + 1} 张好了", {"idx": img.idx, **progress()})
            except Exception as e:  # noqa: BLE001 - 单张失败不影响其他张
                img.status, img.error = ImageStatus.failed, str(e)[:300]
                counter["failed"] += 1
                emit("warning", f"第 {img.idx + 1} 张配图失败：{e}", {"idx": img.idx, **progress()})
            img.updated_at = utcnow()
            session.add(img)
            session.commit()

    async def _review(img: DraftImage, data: bytes, gen, refs: list[str]) -> bytes:
        """出图后看一眼：有错字、内容不对、风格跑偏就带着修改要求重出一次（只重出一次，省额度）。"""
        emit("image", f"第 {img.idx + 1} 张出好了，在自检…", {"idx": img.idx, **progress()})
        res = await visual_mod.check_image(vllm, data, img.expanded_prompt, spec, refs=refs)
        review = {**res, "redone": False, "at": utcnow().isoformat()}
        if not res["ok"] and res.get("fix"):
            emit("image", f"第 {img.idx + 1} 张自检发现：{'；'.join(res['problems'][:2]) or res['fix'][:30]}，改一下重出…",
                 {"idx": img.idx, **progress()})
            prompt2 = f"{img.expanded_prompt}\n【上一版的问题，这次一定要改掉】{res['fix']}"
            try:
                data2 = await gen(prompt2)
            except ImageError as e:
                logger.info("自检后重出失败，留第一版：%s", e)
            else:
                res2 = await visual_mod.check_image(vllm, data2, img.expanded_prompt, spec, refs=refs)
                review = {**res2, "redone": True, "before": res["problems"], "fix": res["fix"], "at": utcnow().isoformat()}
                img.expanded_prompt, data = prompt2, data2
        img.review = review
        return data

    first: list[DraftImage] = []
    if anchor["img"] is None and (not molds or tpl) and len(targets) > 1 and final[targets[0].idx] == "ai" \
            and sum(final[i.idx] == "ai" for i in targets) > 1:
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
    return {**counter, "skipped": len(skip)}
