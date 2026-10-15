"""AI 配图：中文画面描述 → 扩写成英文提示词 → 生图服务 → 存到本地 data/images。

生图服务抽象成 ImageProvider，默认实现是 v1 用的 grsai 节点（gpt-image-2）。
要换别家，实现一个 generate(prompt) -> bytes 即可。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Protocol
from uuid import uuid4

import httpx
from sqlmodel import Session, col, select

from mediaflow.agents import prompts
from mediaflow.config import Settings, get_settings
from mediaflow.domain.models import Account, Draft, DraftImage, ImageStatus, utcnow
from mediaflow.llm.client import LLM, LLMError

logger = logging.getLogger(__name__)


class ImageError(RuntimeError):
    pass


class ImageProvider(Protocol):
    async def generate(self, prompt: str) -> bytes: ...


class GrsaiProvider:
    """提交任务 → 轮询 → 下载。"""

    def __init__(self, settings: Settings | None = None) -> None:
        self.s = settings or get_settings()
        if not self.s.image_api_key:
            raise ImageError("没有配置 IMAGE_API_KEY")

    async def generate(self, prompt: str) -> bytes:
        headers = {"Authorization": f"Bearer {self.s.image_api_key}"}
        async with httpx.AsyncClient(timeout=90) as c:
            r = await c.post(self.s.image_endpoint, headers=headers, json={
                "model": self.s.image_model, "prompt": prompt,
                "aspectRatio": self.s.image_size, "replyType": "json",
            })
            if r.status_code >= 400:
                raise ImageError(f"生图接口 HTTP {r.status_code}：{r.text[:200]}")
            data = r.json()
            loop = asyncio.get_running_loop()
            deadline = loop.time() + self.s.image_timeout
            query = self.s.image_endpoint.replace("/generate", "/query")
            while data.get("status") != "succeeded":
                if data.get("status") in ("failed", "violation"):
                    raise ImageError(f"生图失败：{data.get('error') or data.get('status')}")
                if loop.time() > deadline:
                    raise ImageError("生图超时")
                await asyncio.sleep(3)
                q = await c.post(query, headers=headers, json={"id": data.get("id")}, timeout=15)
                if q.status_code < 400:
                    data = q.json()
            results = data.get("results") or []
            if not results:
                raise ImageError("生图接口没有返回图片")
            first = results[0]
            url = first if isinstance(first, str) else (first.get("url") or first.get("imageUrl") or "")
            if not url:
                raise ImageError("生图结果里没有图片地址")
            img = await c.get(url, timeout=60)
            img.raise_for_status()
            return img.content


_provider_factory: Callable[[], ImageProvider] | None = None


def get_provider() -> ImageProvider:
    if _provider_factory is not None:
        return _provider_factory()
    return GrsaiProvider()


def set_provider_factory(f: Callable[[], ImageProvider] | None) -> None:
    global _provider_factory
    _provider_factory = f


async def _expand(llm: LLM, image_style: str, title: str, img: DraftImage, total: int) -> str:
    try:
        r = await llm.complete([
            {"role": "system", "content": prompts.IMAGE_PROMPT_SYSTEM},
            {"role": "user", "content": prompts.IMAGE_PROMPT_USER.format(
                image_style=image_style or "authentic smartphone photo, natural light",
                title=title, idx=img.idx + 1, total=total,
                cover="（cover, eye-catching）" if img.idx == 0 else "", prompt=img.prompt,
            )},
        ], temperature=0.5)
        return r.content.strip() or img.prompt
    except LLMError as e:
        logger.warning("提示词扩写失败，用原始描述：%s", e)
        return img.prompt


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
    if not get_settings().image_configured:
        for i in targets:
            i.status = ImageStatus.skipped
            session.add(i)
        session.commit()
        emit("warning", "没有配置配图服务（IMAGE_API_KEY），跳过配图", None)
        return {"done": 0, "failed": 0, "skipped": len(targets)}

    provider = get_provider()
    out_dir = get_settings().images_dir / draft_id
    out_dir.mkdir(parents=True, exist_ok=True)
    done = failed = 0
    for img in targets:
        emit("image", f"第 {img.idx + 1}/{len(images)} 张配图生成中…", {"idx": img.idx})
        img.status, img.error, img.updated_at = ImageStatus.running, "", utcnow()
        session.add(img)
        session.commit()
        img.expanded_prompt = await _expand(llm, account.image_style if account else "", draft.title, img, len(images))
        try:
            data = await provider.generate(img.expanded_prompt)
            name = f"{img.idx:02d}-{uuid4().hex[:8]}.png"
            (out_dir / name).write_bytes(data)
            img.path = f"{draft_id}/{name}"
            img.status = ImageStatus.done
            done += 1
        except Exception as e:  # noqa: BLE001 - 单张失败不影响其他张
            img.status, img.error = ImageStatus.failed, str(e)[:300]
            failed += 1
            emit("warning", f"第 {img.idx + 1} 张配图失败：{e}", {"idx": img.idx})
        img.updated_at = utcnow()
        session.add(img)
        session.commit()
    return {"done": done, "failed": failed, "skipped": 0}
