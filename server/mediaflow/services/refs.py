"""配图参考图：把对标账号爆款笔记的原图（封面、内页）下载到本地，出图时作为参考图一起传给生图模型，
让它学对方的版式、配色、字体和构图。

- 小红书图片地址带时间戳会过期，所以第一次用到就缓存到 data/images/_refs，以后直接读本地；
- 统一转成最长边 1024 的 JPEG，体积小、各家模型都认；
- 复刻选题对应的那篇原爆款的图排在最前面，其次按点赞排的其他爆款。
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import logging
from dataclasses import dataclass, field

import httpx
from sqlmodel import Session, select

from mediaflow.config import get_settings
from mediaflow.domain.models import Benchmark, BenchmarkStatus, Topic
from mediaflow.research.types import count_num

logger = logging.getLogger(__name__)

MAX_COVER_REFS = 3   # 封面参考几张对标封面
MAX_INNER_REFS = 3   # 内页参考几张对标内页
_HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/124.0 Safari/537.36", "Referer": "https://www.xiaohongshu.com/"}


@dataclass
class Refs:
    cover: list[str] = field(default_factory=list)   # data URI
    inner: list[str] = field(default_factory=list)

    def for_image(self, idx: int) -> list[str]:
        return self.cover if idx == 0 else (self.inner or self.cover)

    def __bool__(self) -> bool:
        return bool(self.cover or self.inner)


def _key(url: str) -> str:
    # 小红书图片地址形如 https://sns-webpic-qc.xhscdn.com/<时间戳>/<签名>/<图片ID>!nd_dft_wlteh_webp_3，
    # 只有图片 ID 是稳定的，用它做缓存键
    tail = url.split("?")[0].rstrip("/").rsplit("/", 1)[-1].split("!")[0]
    return hashlib.sha1((tail or url).encode()).hexdigest()[:16]


def _to_jpeg(data: bytes) -> bytes:
    from PIL import Image

    im = Image.open(io.BytesIO(data))
    im = im.convert("RGB")
    im.thumbnail((1024, 1024))
    out = io.BytesIO()
    im.save(out, "JPEG", quality=85)
    return out.getvalue()


async def _fetch(c: httpx.AsyncClient, url: str) -> bytes | None:
    d = get_settings().images_dir / "_refs"
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{_key(url)}.jpg"
    if path.exists():
        return path.read_bytes()
    try:
        r = await c.get(url)
        r.raise_for_status()
        data = await asyncio.to_thread(_to_jpeg, r.content)
    except Exception as e:  # noqa: BLE001 - 参考图拿不到就少一张，不影响出图
        logger.info("参考图下载失败 %s：%s", url[:80], e)
        return None
    path.write_bytes(data)
    return data


def _uri(data: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(data).decode()


def _urls(session: Session, account_id: str, topic: Topic | None) -> tuple[list[str], list[str]]:
    benches = session.exec(select(Benchmark).where(
        Benchmark.account_id == account_id, Benchmark.status == BenchmarkStatus.ready)).all()
    samples = [x for b in benches for x in b.samples or [] if x.get("kind") != "视频"]
    samples.sort(key=lambda x: -count_num(x.get("likes")))
    ref = (topic.reference if topic else None) or {}
    first = [x for x in samples if ref.get("url") and x.get("url") == ref.get("url")] or ([ref] if ref.get("cover") else [])
    ordered = first + [x for x in samples if x not in first]
    covers, inner = [], []
    for x in ordered:
        imgs = list(x.get("images") or [])
        c = x.get("cover") or (imgs[0] if imgs else "")
        if c and c not in covers:
            covers.append(c)
        inner += [u for u in imgs[1:4] if u not in inner]
    return covers, inner


async def collect(session: Session, account_id: str, topic: Topic | None = None) -> Refs:
    """这个账号出图要参考的对标原图。没有对标或图都拿不到时返回空。"""
    covers, inner = _urls(session, account_id, topic)
    if not covers and not inner:
        return Refs()
    out = Refs()
    async with httpx.AsyncClient(timeout=15, headers=_HEADERS, follow_redirects=True) as c:
        for urls, dst, n in ((covers, out.cover, MAX_COVER_REFS), (inner, out.inner, MAX_INNER_REFS)):
            for u in urls[: n * 2]:  # 多试几张，有的会过期
                if len(dst) >= n:
                    break
                data = await _fetch(c, u)
                if data:
                    dst.append(_uri(data))
    return out
