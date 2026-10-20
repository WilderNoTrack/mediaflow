"""网上找图：按关键词去图片搜索（360 图片 → 必应）找真实照片，挑一张合适的，裁成 3:4 当底图，再用代码叠字（layout.py）。

- 能看图时让看图模型从几张候选里挑：内容贴合、清楚、没有水印和大段文字的
- 记下图片出处（网址、来自哪个网站），草稿页会标出来。网上的图版权归原作者，发之前自己确认能不能用；
  商用或者怕侵权，就换成自己拍的图，或者改用「排版卡片」/「AI 画」
"""

from __future__ import annotations

import asyncio
import html
import io
import json
import logging
import re
from urllib.parse import quote, urlparse

import httpx
from PIL import Image

from mediaflow.llm.client import LLM, LLMError, complete_json, image_part

logger = logging.getLogger(__name__)

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
       "Chrome/124.0 Safari/537.36")
MIN_SIDE = 560  # 太小的图放大了糊
_BAD_SITES = ("xiaohongshu.com", "xhscdn.com")  # 别人的小红书笔记图不拿来用


class WebImageError(RuntimeError):
    pass


def _num(v) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def parse_360(data: dict) -> list[dict]:
    out = []
    for r in (data or {}).get("list") or []:
        url = r.get("img") or r.get("qhimg_url") or ""
        if not url:
            continue
        out.append({"url": url, "thumb": r.get("_thumb") or r.get("thumb") or "", "title": html.unescape(str(r.get("title") or ""))[:60],
                    "width": _num(r.get("width")), "height": _num(r.get("height")),
                    "site": r.get("site") or urlparse(r.get("link") or url).netloc, "link": r.get("link") or "", "engine": "360"})
    return out


_IUSC = re.compile(r'class="iusc"[^>]*?\sm="([^"]+)"|\sm="([^"]+)"[^>]*?class="iusc"')


def parse_bing(text: str) -> list[dict]:
    out = []
    for a, b in _IUSC.findall(text or ""):
        try:
            m = json.loads(html.unescape(a or b))
        except ValueError:
            continue
        url = m.get("murl") or ""
        if not url:
            continue
        link = m.get("purl") or ""
        out.append({"url": url, "thumb": m.get("turl") or "", "title": str(m.get("t") or "")[:60], "width": 0, "height": 0,
                    "site": urlparse(link or url).netloc, "link": link, "engine": "bing"})
    return out


async def search(query: str, *, client: httpx.AsyncClient | None = None, limit: int = 30) -> list[dict]:
    """搜图：先 360 图片，结果太少再用必应。返回 [{url, thumb, title, width, height, site, link, engine}]。"""
    own = client is None
    c = client or httpx.AsyncClient(timeout=15, headers={"User-Agent": _UA, "Accept-Language": "zh-CN,zh;q=0.9"},
                                    follow_redirects=True)
    out: list[dict] = []
    try:
        try:
            r = await c.get(f"https://image.so.com/j?q={quote(query)}&src=srp&pn={limit}&sn=0")
            out += parse_360(r.json())
        except (httpx.HTTPError, ValueError) as e:
            logger.info("360 图片搜不了：%s", e)
        if len(out) < 6:
            try:
                r = await c.get(f"https://cn.bing.com/images/async?q={quote(query)}&first=0&count={limit}&mmasync=1")
                out += parse_bing(r.text)
            except httpx.HTTPError as e:
                logger.info("必应图片搜不了：%s", e)
    finally:
        if own:
            await c.aclose()
    seen, uniq = set(), []
    for x in out:
        if x["url"] in seen or any(s in x["url"] or s in x["site"] for s in _BAD_SITES):
            continue
        seen.add(x["url"])
        uniq.append(x)
    return uniq


def _usable(x: dict) -> bool:
    w, h = x.get("width") or 0, x.get("height") or 0
    if not w or not h:
        return True  # 不知道尺寸的下载下来再看
    return min(w, h) >= MIN_SIDE and 0.45 <= w / h <= 1.8


def _rank(x: dict) -> float:
    """竖图、大图优先（裁成 3:4 损失少）。"""
    w, h = x.get("width") or 800, x.get("height") or 800
    ratio = w / h
    return -abs(ratio - 0.75) * 2 + min(w * h, 2_500_000) / 2_500_000


async def _download(c: httpx.AsyncClient, x: dict) -> bytes | None:
    for url in (x["url"], x.get("thumb") or ""):
        if not url:
            continue
        try:
            r = await c.get(url, headers={"Referer": x.get("link") or f"https://{x.get('site') or ''}/"}, timeout=20)
            r.raise_for_status()
            img = Image.open(io.BytesIO(r.content))
            img.load()
        except (httpx.HTTPError, OSError, ValueError):
            continue
        if min(img.size) >= (MIN_SIDE if url == x["url"] else 400):
            buf = io.BytesIO()
            img.convert("RGB").save(buf, "JPEG", quality=92)
            return buf.getvalue()
    return None


PICK_PROMPT = """要给一篇小红书笔记的一张配图找真实照片当底图，上面会再用代码排字。这张图要表现：{want}
下面依次是 {n} 张候选图（第 1 张到第 {n} 张）。挑最合适的一张：内容贴合要表现的东西、清楚好看、有生活感；
不要：有水印/logo、图上本身有字（信息图、表格、带标题的配图，上面还要排字会打架）、拼图截图海报、明显是别人的笔记封面、人脸特写（肖像权）、低俗血腥的。
画面越干净（主体清楚、留有空白处）越好。
都不合适就 pick 填 0。只输出 JSON：{{"pick": 第几张, "why": "一句话"}}"""


async def _pick(vllm: LLM, want: str, cands: list[tuple[dict, bytes]]) -> int:
    from mediaflow.services.refs import uri_of

    uris = [await asyncio.to_thread(uri_of, b) for _, b in cands]
    parts = [{"type": "text", "text": PICK_PROMPT.format(want=want[:200], n=len(cands))},
             *[image_part(u) for u in uris if u]]
    try:
        raw = await complete_json(vllm, [{"role": "user", "content": parts}], temperature=0.1)
        k = int(raw.get("pick") or 0)
    except (LLMError, TypeError, ValueError) as e:
        logger.info("看图挑底图没做成，用第一张：%s", e)
        return 1
    return k if 0 <= k <= len(cands) else 1


async def find_photo(queries: list[str], want: str, *, vllm: LLM | None = None, avoid: set[str] | None = None,
                     tries: int = 4) -> tuple[bytes, dict]:
    """按关键词找一张能用的照片：返回 (图片 JPEG, 出处 {url, link, site, title, query, engine})。找不到抛 WebImageError。"""
    avoid = avoid or set()
    qs = [q.strip() for q in queries if q and q.strip()][:3]
    if not qs:
        raise WebImageError("没有搜图关键词")
    async with httpx.AsyncClient(timeout=15, headers={"User-Agent": _UA, "Accept-Language": "zh-CN,zh;q=0.9"},
                                 follow_redirects=True) as c:
        for q in qs:
            found = [x for x in await search(q, client=c) if x["url"] not in avoid and _usable(x)]
            found.sort(key=_rank, reverse=True)
            got: list[tuple[dict, bytes]] = []
            for x in found[: tries * 2]:
                b = await _download(c, x)
                if b:
                    got.append((x, b))
                if len(got) >= (tries if vllm else 1):
                    break
            if not got:
                continue
            k = await _pick(vllm, want, got) if vllm is not None and len(got) > 1 else 1
            if k == 0:
                logger.info("「%s」搜到的图都不合适，换个词", q)
                continue
            x, b = got[k - 1]
            return b, {"url": x["url"], "link": x.get("link", ""), "site": x.get("site", ""), "title": x.get("title", ""),
                       "query": q, "engine": x.get("engine", "")}
    raise WebImageError(f"网上没找到合适的图（搜了：{'、'.join(qs)}）")
