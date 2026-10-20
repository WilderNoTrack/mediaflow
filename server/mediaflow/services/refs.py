"""参考图的下载和编码：主参考帖的原图缓存到本地，出图时当版式模板传给生图模型（选哪篇见 refpost.py）。

- 小红书图片地址带时间戳会过期，所以第一次用到就缓存到 data/images/_refs，以后直接读本地；
- 统一转成最长边 1024 的 JPEG，体积小、各家模型都认。
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import logging

import httpx

from mediaflow.config import get_settings

logger = logging.getLogger(__name__)

_HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/124.0 Safari/537.36", "Referer": "https://www.xiaohongshu.com/"}


def _referer(url: str) -> str:
    """各家图床认自己的 Referer（微博图床见到别家的 Referer 会 403）。"""
    if "sinaimg.cn" in url:
        return "https://weibo.com/"
    if "douyinpic.com" in url or "douyin" in url:
        return "https://www.douyin.com/"
    return "https://www.xiaohongshu.com/"


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
        r = await c.get(url, headers={"Referer": _referer(url)})
        r.raise_for_status()
        data = await asyncio.to_thread(_to_jpeg, r.content)
    except Exception as e:  # noqa: BLE001 - 参考图拿不到就少一张，不影响出图
        logger.info("参考图下载失败 %s：%s", url[:80], e)
        return None
    path.write_bytes(data)
    return data


async def cache_local(urls: list[str]) -> list[str]:
    """把原图下载缓存到 data/images/_refs，返回相对 data/images 的路径（拿不到的跳过）。"""
    out: list[str] = []
    async with httpx.AsyncClient(timeout=15, headers=_HEADERS, follow_redirects=True) as c:
        for u in urls:
            if u and await _fetch(c, u):
                out.append(f"_refs/{_key(u)}.jpg")
    return out


def local_uri(rel: str) -> str | None:
    """_refs/xxx.jpg → data URI（给生图模型当参考图）。"""
    path = get_settings().images_dir / rel
    return _uri(path.read_bytes()) if rel.startswith("_refs/") and path.exists() else None


def _uri(data: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(data).decode()


def uri_of(data: bytes) -> str | None:
    """已经出好的图（PNG 等）→ 压成 JPEG 的 data URI，当同一套图的风格参照；读不了就不带。"""
    try:
        return _uri(_to_jpeg(data))
    except Exception:  # noqa: BLE001
        return None
