"""B站调研能力：搜 UP 主 / UP 主投稿 / 视频详情（WBI 签名与游客 buvid 复用 BilibiliSource）。

接口参考 SocialSisterYi/bilibili-API-collect。投稿列表接口风控较严，需要带 dm_img_* 这组浏览器指纹参数，
否则容易 -352。
"""

from __future__ import annotations

import asyncio
import hashlib
import html
import re
import time
from contextlib import asynccontextmanager
from urllib.parse import quote

import httpx

from mediaflow.research.types import Creator, Post, PostDetail, count_num, fmt_count, ms_date
from mediaflow.sources.base import DESKTOP_UA

API = "https://api.bilibili.com"
_TAG = re.compile(r"<[^>]+>")
# 网页端 WebGL 指纹（base64），见 bilibili-API-collect 的 docs/misc/sign/wbi.md 讨论
_DM = {"dm_img_list": "[]", "dm_img_str": "V2ViR0wgMS4wIChPcGVuR0wgRVMgMi4wIENocm9taXVtKQ",
       "dm_cover_img_str": "QU5HTEUgKEdvb2dsZSwgVnVsa2FuIDEuMy4wIChTd2lmdFNoYWRlciBEZXZpY2UgKFN1Ymd6ZXJvKSAoMHgwMDAwQzBERSkpLCBTd2lmdFNoYWRlciBkcml2ZXIpR29vZ2xlIEluYy4gKEdvb2dsZS"}


def _src():
    from mediaflow.sources.platforms import BilibiliSource
    return BilibiliSource()


@asynccontextmanager
async def _client(timeout: float):
    async with httpx.AsyncClient(timeout=timeout, headers={"User-Agent": DESKTOP_UA,
                                                           "Referer": "https://www.bilibili.com"}) as c:
        await _src()._ensure_buvid(c)
        yield c


async def _signed(c: httpx.AsyncClient, params: dict) -> dict:
    mk = await _src()._mixin_key(c)
    params = {**params, "wts": int(time.time())}
    qs = "&".join(f"{k}={quote(str(v), safe='')}" for k, v in sorted(params.items()))
    params["w_rid"] = hashlib.md5((qs + mk).encode()).hexdigest()
    return params


async def _json(c: httpx.AsyncClient, url: str, params: dict, what: str) -> dict:
    r = await c.get(url, params=params)
    r.raise_for_status()
    j = r.json()
    if j.get("code") not in (0, None):
        hint = "（被风控了，稍后再试；在「数据来源」扫码登录 B站会更稳）" if j.get("code") in (-352, -412, -799) else ""
        raise RuntimeError(f"B站{what}失败：{j.get('message') or j.get('code')}{hint}")
    return j.get("data") or {}


def _text(s) -> str:
    return " ".join(html.unescape(_TAG.sub("", str(s or ""))).split())


async def search_creators(name: str, limit: int = 5, timeout: float = 15):
    async with _client(timeout) as c:
        d = await _json(c, f"{API}/x/web-interface/wbi/search/type",
                        await _signed(c, {"search_type": "bili_user", "keyword": name, "page": 1}), "搜UP主")
    return [Creator(platform="bilibili", name=_text(u.get("uname")), native=str(u["mid"]),
                    fans=fmt_count(u.get("fans", "")), posts=str(u.get("videos", "")),
                    desc=_text(u.get("usign"))[:200], url=f"https://space.bilibili.com/{u['mid']}")
            for u in (d.get("result") or []) if u.get("mid")][:limit]


async def creator_posts(native: str, limit: int = 10, timeout: float = 15):
    async with _client(timeout) as c:
        card = await _json(c, f"{API}/x/web-interface/card", {"mid": native}, "看UP主主页")
        await asyncio.sleep(0.8)
        d = await _json(c, f"{API}/x/space/wbi/arc/search", await _signed(c, {
            "mid": native, "ps": 30, "pn": 1, "order": "pubdate", "platform": "web", **_DM}), "看UP主投稿")
    info = card.get("card") or {}
    creator = Creator(platform="bilibili", name=info.get("name", ""), native=native,
                      fans=fmt_count(card.get("follower", "")), posts=str(card.get("archive_count", "")),
                      desc=_text(info.get("sign"))[:200], url=f"https://space.bilibili.com/{native}",
                      extra={"获赞": fmt_count(card.get("like_num", ""))})
    posts = [Post(platform="bilibili", title=_text(v.get("title")), native=v["bvid"], author=creator.name,
                  url=f"https://www.bilibili.com/video/{v['bvid']}", views=fmt_count(v.get("play", "")),
                  comments=fmt_count(v.get("comment", "")), published=ms_date(v.get("created")), kind="视频")
             for v in ((d.get("list") or {}).get("vlist") or []) if v.get("bvid")]
    return creator, posts[:limit]


async def post_detail(native: str, comments: int = 8, timeout: float = 15):
    async with _client(timeout) as c:
        v = await _json(c, f"{API}/x/web-interface/view", {"bvid": native}, "看视频详情")
        tags = await _json(c, f"{API}/x/tag/archive/tags", {"bvid": native}, "看视频标签")
        await asyncio.sleep(0.8)
        rp = await _json(c, f"{API}/x/v2/reply", {"type": 1, "oid": v.get("aid"), "sort": 1, "ps": 20}, "看评论")
    st = v.get("stat") or {}
    top = sorted(rp.get("replies") or [], key=lambda x: -count_num(x.get("like")))
    return PostDetail(
        platform="bilibili", title=_text(v.get("title")), native=native,
        url=f"https://www.bilibili.com/video/{native}", author=(v.get("owner") or {}).get("name", ""),
        views=fmt_count(st.get("view", "")), likes=fmt_count(st.get("like", "")),
        comments=fmt_count(st.get("reply", "")), collects=fmt_count(st.get("favorite", "")),
        shares=fmt_count(st.get("share", "")), published=ms_date(v.get("pubdate")), kind="视频",
        content=(v.get("desc") or "").strip()[:1500],
        tags=[t.get("tag_name") for t in (tags if isinstance(tags, list) else []) if t.get("tag_name")],
        top_comments=[f"{x.get('like', 0)}赞｜{_text((x.get('content') or {}).get('message'))[:120]}"
                      for x in top[:comments] if (x.get("content") or {}).get("message")],
    )
