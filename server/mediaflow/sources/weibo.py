"""微博调研能力：搜博主 / 博主微博 / 微博详情。需要在「数据来源」里填微博 Cookie。

网页版 ajax 接口要带 Cookie + X-XSRF-TOKEN（取自 Cookie 里的 XSRF-TOKEN）+ X-Requested-With，
搜用户只有 HTML 页（s.weibo.com/user），用 BeautifulSoup 解析卡片。
"""

from __future__ import annotations

import asyncio
import html
import re
from datetime import datetime

import httpx

from mediaflow.research.types import Creator, Post, PostDetail, Unsupported, count_num, fmt_count
from mediaflow.sources.base import DESKTOP_UA

W = "https://weibo.com"
_TAG = re.compile(r"<[^>]+>")


def _cookie() -> str:
    from mediaflow.sources.platforms import credentials
    ck = credentials.get("weibo_cookie")
    if not ck:
        raise Unsupported("微博没登录，请先在「数据来源」里填微博 Cookie")
    return ck


def _client(timeout: float) -> httpx.AsyncClient:
    ck = _cookie()
    xsrf = dict(p.strip().split("=", 1) for p in ck.split(";") if "=" in p).get("XSRF-TOKEN", "")
    return httpx.AsyncClient(timeout=timeout, follow_redirects=False, headers={
        "User-Agent": DESKTOP_UA, "Cookie": ck, "Referer": f"{W}/", "X-Requested-With": "XMLHttpRequest",
        "X-XSRF-TOKEN": xsrf, "Accept": "application/json, text/plain, */*"})


async def _json(c: httpx.AsyncClient, path: str, params: dict, what: str) -> dict:
    r = await c.get(f"{W}{path}", params=params)
    if r.status_code in (301, 302, 403) or "json" not in r.headers.get("content-type", ""):
        raise RuntimeError(f"微博{what}失败：Cookie 可能过期了，请在「数据来源」里重新填写")
    r.raise_for_status()
    j = r.json()
    if j.get("ok") not in (1, None):
        raise RuntimeError(f"微博{what}失败：{j.get('msg') or j.get('message') or j.get('ok')}")
    return j


def _text(s) -> str:
    return " ".join(html.unescape(_TAG.sub("", str(s or ""))).split())


def _date(s: str) -> str:
    try:
        return datetime.strptime(s, "%a %b %d %H:%M:%S %z %Y").strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return ""


def _kind(m: dict) -> str:
    pi = m.get("page_info") or {}
    if pi.get("object_type") == "video" or pi.get("type") == "video":
        return "视频"
    if m.get("retweeted_status"):
        return "转发"
    return "图文" if m.get("pic_num") else "文字"


def _fmt(n) -> str:
    return fmt_count(n) if isinstance(n, int) else str(n or "")


def _pic(pid: str, size: str = "orj360") -> str:
    return f"https://wx1.sinaimg.cn/{size}/{pid}.jpg" if pid else ""


def _pics(m: dict, size: str = "large") -> list[str]:
    """一条微博的配图地址；size=orj360 是列表里用的小图（封面），large 是原图（学配图模板用）。"""
    infos = m.get("pic_infos") or {}
    out = []
    for pid in m.get("pic_ids") or []:
        info = infos.get(pid) or {}
        url = (info.get(size) or {}).get("url") if size in info else ""
        out.append(url or (_pic(pid, size) if size == "orj360" else ((info.get("largest") or {}).get("url") or _pic(pid, size))))
    return [u for u in out if u]


async def search_hot_authors(keyword: str, timeout: float = 15) -> list[dict]:
    """按关键词搜微博「热门」，带出作者（找同领域对标账号用）。只留带图的微博——我们做的是图文号。"""
    from bs4 import BeautifulSoup

    async with _client(timeout) as c:
        r = await c.get("https://s.weibo.com/weibo", params={"q": keyword, "xsort": "hot", "suball": "1", "Refer": "g"})
    if r.status_code != 200:
        raise RuntimeError("微博搜索失败：Cookie 可能过期了，请在「数据来源」里重新填写")
    out = []
    for card in BeautifulSoup(r.text, "html.parser").select('div.card-wrap[mid]'):
        a = card.select_one("a.name")
        m = re.search(r"weibo\.com/(?:u/)?(\d{5,})", a.get("href", "")) if a else None
        el = card.select_one("p.txt")
        if not m or not el:
            continue
        text = re.sub(r"\s*(全文|收起)\s*$", "", el.get_text(" ", strip=True)).strip()
        pics = [i.get("src", "") for i in card.select("div.media img") if i.get("src")]
        video = card.select_one("div.media video, div.media [action-data*=video], .WB_video")
        acts = [li.get_text(strip=True) for li in card.select("div.card-act li")]
        link = card.select_one("div.from a[href]")
        href = link["href"] if link else ""
        avatar = card.select_one("div.avator img")
        out.append({"user_id": m.group(1), "name": a.get_text(strip=True), "native": m.group(1),
                    "avatar": avatar.get("src", "") if avatar else "", "title": text[:60],
                    "likes": re.sub(r"\D", "", acts[-1]) if acts else "", "cover": ("https:" + pics[0]) if pics and pics[0].startswith("//") else (pics[0] if pics else ""),
                    "kind": "视频" if video else ("图文" if pics else "文字"),
                    "url": ("https:" + href.split("?")[0]) if href.startswith("//") else href.split("?")[0]})
    return out


async def search_creators(name: str, limit: int = 5, timeout: float = 15):
    from bs4 import BeautifulSoup

    async with _client(timeout) as c:
        r = await c.get("https://s.weibo.com/user", params={"q": name})
    if r.status_code != 200:
        raise RuntimeError("微博搜博主失败：Cookie 可能过期了，请在「数据来源」里重新填写")
    out = []
    for card in BeautifulSoup(r.text, "html.parser").select("div.card-user-b"):
        a = card.select_one("a.name")
        m = re.search(r"/u/(\d+)", a.get("href", "")) if a else None
        if not m:
            continue
        ps = [p.get_text(" ", strip=True) for p in card.select("div.info > p")]
        fans = next((re.sub(r"^粉丝：", "", p) for p in ps if p.startswith("粉丝")), "")
        desc = " ".join(p for p in ps if not p.startswith(("粉丝", "关注")))
        verified = card.select_one(".woo-avatar-icon")
        out.append(Creator(platform="weibo", name=a.get_text(strip=True), native=m.group(1), fans=fans,
                           desc=desc[:200], url=f"https://weibo.com/u/{m.group(1)}",
                           extra={"认证": verified.get("title", "") if verified else ""}))
        if len(out) >= limit:
            break
    return out


async def creator_posts(native: str, limit: int = 10, timeout: float = 15):
    async with _client(timeout) as c:
        u = ((await _json(c, "/ajax/profile/info", {"uid": native}, "看博主主页")).get("data") or {}).get("user") or {}
        await asyncio.sleep(0.8)
        d = (await _json(c, "/ajax/statuses/mymblog", {"uid": native, "page": 1, "feature": 0}, "看博主微博")).get("data") or {}
    creator = Creator(platform="weibo", name=u.get("screen_name", ""), native=native,
                      fans=u.get("followers_count_str") or _fmt(u.get("followers_count")),
                      posts=_fmt(u.get("statuses_count")), desc=(u.get("description") or "")[:200],
                      url=f"https://weibo.com/u/{native}", extra={"认证": u.get("verified_reason", "")})
    posts = []
    for m in d.get("list") or []:
        if not m.get("mblogid") or m.get("isTop"):
            continue  # 置顶微博往往很旧，不算近期作品
        posts.append(Post(platform="weibo", title=_text(m.get("text_raw") or m.get("text"))[:80],
                          native=f"{m['mblogid']}|{m.get('id', '')}|{native}", author=creator.name,
                          url=f"https://weibo.com/{native}/{m['mblogid']}", likes=_fmt(m.get("attitudes_count")),
                          comments=_fmt(m.get("comments_count")), shares=_fmt(m.get("reposts_count")),
                          published=_date(m.get("created_at", "")), kind=_kind(m),
                          cover=next(iter(_pics(m, "orj360")), "")))
    return creator, posts[:limit]


async def post_detail(native: str, comments: int = 8, timeout: float = 15):
    mblogid, mid, uid = (native.split("|") + ["", ""])[:3]
    async with _client(timeout) as c:
        m = await _json(c, "/ajax/statuses/show", {"id": mblogid, "isGetLongText": "true"}, "看微博详情")
        mid = mid or str(m.get("id", ""))
        uid = uid or str((m.get("user") or {}).get("id", ""))
        await asyncio.sleep(0.8)
        cm = await _json(c, "/ajax/statuses/buildComments", {
            "is_reload": 1, "id": mid, "is_show_bulletin": 2, "is_mix": 0, "count": 20, "uid": uid,
            "fetch_level": 0, "flow": 0}, "看评论")
    content = (m.get("longText") or {}).get("longTextContent") or m.get("text_raw") or _text(m.get("text"))
    top = sorted(cm.get("data") or [], key=lambda x: -count_num(x.get("like_counts")))
    return PostDetail(
        platform="weibo", title=_text(content)[:80], native=native, url=f"https://weibo.com/{uid}/{mblogid}",
        author=(m.get("user") or {}).get("screen_name", ""), likes=_fmt(m.get("attitudes_count")),
        comments=_fmt(m.get("comments_count")), shares=_fmt(m.get("reposts_count")),
        published=_date(m.get("created_at", "")), kind=_kind(m), content=content.strip()[:1500],
        author_native=uid, images=_pics(m)[:18], cover=next(iter(_pics(m, "orj360")), ""),
        tags=[t["topic_title"] for t in m.get("topic_struct") or [] if t.get("topic_title")],
        top_comments=[f"{x.get('like_counts', 0)}赞｜{_text(x.get('text_raw') or x.get('text'))[:120]}"
                      for x in top[:comments] if x.get("text_raw") or x.get("text")],
    )


_UID = re.compile(r"(?:weibo\.com|weibo\.cn)/(?:u/|profile/)?(\d{5,})(?:[/?#]|$)")
_MBLOG = re.compile(r"weibo\.com/(\d{5,})/([A-Za-z0-9]{8,})")
_MID = re.compile(r"m\.weibo\.cn/(?:detail|status)/([A-Za-z0-9]{8,})")


def resolve_link(text: str) -> tuple[str, str]:
    """把用户贴的微博链接解析成 (kind, native)：creator=主页（uid）、post=一条微博（mblogid||uid）；认不出返回 ("", "")。"""
    m = re.search(r"https?://\S+", text or "")
    if not m:
        return "", ""
    url = m.group(0)
    if p := _MBLOG.search(url):
        return "post", f"{p.group(2)}||{p.group(1)}"
    if p := _MID.search(url):
        return "post", f"{p.group(1)}||"
    if u := _UID.search(url):
        return "creator", u.group(1)
    return "", ""
