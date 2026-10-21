"""抖音网页版接口：统一的签名请求（a_bogus）+ 调研能力（搜博主 / 博主作品 / 作品详情）。

参数与请求头参考 MediaCrawler：webid、uifid、verifyFp/fp 都取自用户 Cookie，并带 uifid / x-tt-argus 头。
实测旧的 X-Bogus 会被判 antispam（hit_shark，返回空列表），所以统一用 a_bogus。
"""

from __future__ import annotations

import asyncio
import re
from urllib.parse import quote, urlencode

import httpx

from mediaflow import credentials

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


def parse_cookie(cookie: str) -> dict[str, str]:
    return dict(p.strip().split("=", 1) for p in cookie.split(";") if "=" in p)


def _base(ck: dict[str, str]) -> dict[str, str]:
    return {
        "device_platform": "webapp", "aid": "6383", "channel": "channel_pc_web",
        "update_version_code": "170400", "pc_client_type": "1", "pc_libra_divert": "Windows",
        "version_code": "190600", "version_name": "19.6.0", "cookie_enabled": "true",
        "screen_width": "1920", "screen_height": "1080", "browser_language": "zh-CN",
        "browser_platform": "Win32", "browser_name": "Chrome", "browser_version": "131.0.0.0",
        "browser_online": "true", "engine_name": "Blink", "engine_version": "131.0.0.0",
        "os_name": "Windows", "os_version": "10", "cpu_core_num": "8", "device_memory": "8",
        "platform": "PC", "downlink": "10", "effective_type": "4g", "round_trip_time": "50",
        "webid": ck.get("webid", ""), "uifid": ck.get("UIFID") or ck.get("UIFID_TEMP", ""),
        "verifyFp": ck.get("s_v_web_id", ""), "fp": ck.get("s_v_web_id", ""), "msToken": ck.get("msToken", ""),
    }


async def api(c: httpx.AsyncClient, path: str, params: dict, cookie: str,
              referer: str = "https://www.douyin.com/") -> dict:
    """带 a_bogus 签名的 GET；返回 JSON，状态码非 0 时抛出可读错误。"""
    from mediaflow.sources.douyin_abogus import ABogus

    ck = parse_cookie(cookie)
    qs = urlencode({**_base(ck), **params})
    url = f"https://www.douyin.com{path}?{qs}&a_bogus={quote(ABogus(UA).get_value(qs), safe='')}"
    headers = {
        "User-Agent": UA, "Cookie": cookie, "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9", "x-tt-argus": "1", "Referer": referer,
        "sec-fetch-site": "same-origin", "sec-fetch-mode": "cors",
    }
    if ck.get("UIFID") or ck.get("UIFID_TEMP"):
        headers["uifid"] = ck.get("UIFID") or ck.get("UIFID_TEMP", "")
    r = await c.get(url, headers=headers)
    r.raise_for_status()
    if not r.text.strip():
        raise RuntimeError("抖音返回空内容，Cookie 可能失效了")
    data = r.json()
    if data.get("status_code") not in (0, None):
        msg = data.get("status_msg") or data.get("status_code")
        raise RuntimeError(f"抖音：{msg}（Cookie 可能过期）")
    if (data.get("search_nil_info") or {}).get("search_nil_type") in ("antispam_check", "verify_check"):
        raise RuntimeError("抖音搜索触发风控、要求人机验证：在浏览器里打开抖音搜一次、过掉验证，稍后再试（必要时重新复制 Cookie）")
    return data


def _need_cookie() -> str:
    from mediaflow.research.types import Unsupported

    cookie = credentials.get("douyin_cookie")
    if not cookie:
        raise Unsupported("抖音没配置 Cookie，请先在「数据来源」里粘贴")
    return cookie


def _clean(s: str) -> str:
    return " ".join((s or "").split())


def _first(d: dict | None) -> str:
    return next(iter((d or {}).get("url_list") or []), "")


def _cover(aw: dict) -> str:
    imgs = aw.get("images") or []
    return _first(imgs[0]) if imgs else _first((aw.get("video") or {}).get("cover"))


def _url(aw: dict) -> str:
    return f"https://www.douyin.com/{'note' if aw.get('images') else 'video'}/{aw.get('aweme_id')}"


def _post(aw: dict, author: str = ""):
    from mediaflow.research.types import Post, fmt_count, ms_date

    st = aw.get("statistics") or {}
    a = aw.get("author") or {}
    return Post(
        platform="douyin", title=_clean(aw.get("desc"))[:80] or "（无文案）", native=str(aw.get("aweme_id")),
        url=_url(aw), author=author or a.get("nickname", ""),
        likes=fmt_count(st.get("digg_count", "")), comments=fmt_count(st.get("comment_count", "")),
        collects=fmt_count(st.get("collect_count", "")), shares=fmt_count(st.get("share_count", "")),
        published=ms_date(aw.get("create_time")), kind="图文" if aw.get("images") else "视频",
        author_native=a.get("sec_uid", ""), cover=_cover(aw),
    )


# 综合搜索只看图文（content_type=2）：我们做的是图文号，抖音上的图文博主才学得来
_IMAGE_ONLY = '{"sort_type":"0","publish_time":"0","filter_duration":"","search_range":"0","content_type":"2"}'


async def search_hot_authors(keyword: str, timeout: float = 15) -> list[dict]:
    """按关键词搜抖音上的热门图文，带出作者（找同领域对标账号用）。"""
    from mediaflow.research.types import fmt_count

    cookie = _need_cookie()
    async with httpx.AsyncClient(timeout=timeout) as c:
        for attempt in range(2):  # 偶尔无理由返回空列表，重试一次通常就有
            data = await api(c, "/aweme/v1/web/general/search/single/", {
                "search_channel": "aweme_general", "enable_history": "1", "keyword": keyword,
                "search_source": "tab_search", "query_correct_type": "1", "is_filter_search": "1",
                "from_group_id": "", "offset": "0", "count": "20", "need_filter_settings": "1", "list_type": "multi",
                "filter_selected": _IMAGE_ONLY,
            }, cookie, referer=f"https://www.douyin.com/search/{quote(keyword)}?type=general")
            if data.get("data") or attempt:
                break
            await asyncio.sleep(1)
    out = []
    for raw in data.get("data") or []:
        aw = raw.get("aweme_info") if isinstance(raw, dict) else None
        a = (aw or {}).get("author") or {}
        title = _clean((aw or {}).get("desc"))
        if not aw or not a.get("sec_uid") or not title:
            continue
        out.append({"user_id": a["sec_uid"], "name": a.get("nickname", ""), "avatar": _first(a.get("avatar_thumb")),
                    "native": a["sec_uid"], "title": title[:60],
                    "likes": fmt_count((aw.get("statistics") or {}).get("digg_count", "")),
                    "cover": _cover(aw), "kind": "图文" if aw.get("images") else "视频", "url": _url(aw)})
    return out


async def search_creators(name: str, limit: int = 5, timeout: float = 15):
    from mediaflow.research.types import Creator, fmt_count

    cookie = _need_cookie()
    async with httpx.AsyncClient(timeout=timeout) as c:
        data = await api(c, "/aweme/v1/web/discover/search/", {
            "search_channel": "aweme_user_web", "keyword": name, "search_source": "normal_search",
            "query_correct_type": "1", "is_filter_search": "0", "offset": "0", "count": "10",
        }, cookie, referer=f"https://www.douyin.com/search/{quote(name)}?type=user")
    out = []
    for row in data.get("user_list") or []:
        u = row.get("user_info") or {}
        if not u.get("sec_uid"):
            continue
        out.append(Creator(
            platform="douyin", name=u.get("nickname", ""), native=u["sec_uid"],
            fans=fmt_count(u.get("follower_count", "")), desc=_clean(u.get("signature"))[:200],
            url=f"https://www.douyin.com/user/{u['sec_uid']}",
            extra={"抖音号": u.get("unique_id") or u.get("short_id") or "",
                   "获赞": fmt_count(u.get("total_favorited", ""))},
        ))
    return out[:limit]


async def creator_posts(native: str, limit: int = 10, timeout: float = 15):
    from mediaflow.research.types import Creator, fmt_count

    cookie = _need_cookie()
    ref = f"https://www.douyin.com/user/{native}"
    async with httpx.AsyncClient(timeout=timeout) as c:
        prof = await api(c, "/aweme/v1/web/user/profile/other/", {
            "sec_user_id": native, "publish_video_strategy_type": "2",
            "personal_center_strategy": "1", "profile_other_record_enable": "1",
        }, cookie, referer=ref)
        await asyncio.sleep(0.8)
        data = await api(c, "/aweme/v1/web/aweme/post/", {
            "sec_user_id": native, "max_cursor": "0", "count": "18", "locate_query": "false",
            "show_live_replay_strategy": "1", "need_time_list": "1", "time_list_query": "0",
            "whale_cut_token": "", "cut_version": "1", "publish_video_strategy_type": "2",
        }, cookie, referer=ref)
    u = prof.get("user") or {}
    creator = Creator(
        platform="douyin", name=u.get("nickname", ""), native=native,
        fans=fmt_count(u.get("follower_count", "")), desc=_clean(u.get("signature"))[:200],
        posts=str(u.get("aweme_count", "")), url=ref,
        extra={"获赞": fmt_count(u.get("total_favorited", "")), "IP 属地": u.get("ip_location", "")},
    )
    posts = [_post(aw, creator.name) for aw in data.get("aweme_list") or [] if aw.get("aweme_id")]
    return creator, posts[:limit]


async def post_detail(native: str, comments: int = 8, timeout: float = 15):
    from mediaflow.research.types import PostDetail, count_num

    cookie = _need_cookie()
    async with httpx.AsyncClient(timeout=timeout) as c:
        d = await api(c, "/aweme/v1/web/aweme/detail/", {"aweme_id": native}, cookie,
                      referer=f"https://www.douyin.com/video/{native}")
        aw = d.get("aweme_detail") or {}
        if not aw:
            raise RuntimeError("抖音没有返回这条作品（可能已删除或设为私密）")
        await asyncio.sleep(0.8)
        cm = await api(c, "/aweme/v1/web/comment/list/", {
            "aweme_id": native, "cursor": "0", "count": "20", "item_type": "0"}, cookie,
            referer=f"https://www.douyin.com/video/{native}")
    base = _post(aw)
    top = sorted(cm.get("comments") or [], key=lambda x: -count_num(x.get("digg_count")))
    return PostDetail(
        **base.__dict__, content=(aw.get("desc") or "").strip()[:1500],
        images=[u for u in (_first(im) for im in aw.get("images") or []) if u][:18],
        tags=[t["hashtag_name"] for t in aw.get("text_extra") or [] if t.get("hashtag_name")],
        top_comments=[f"{x.get('digg_count', 0)}赞｜{_clean(x.get('text'))[:120]}" for x in top[:comments] if x.get("text")],
    )


_USER = re.compile(r"douyin\.com/(?:share/)?user/([\w\-]{20,})")
_ITEM = re.compile(r"(?:douyin\.com/(?:share/)?(?:video|note|slides)/|modal_id=|aweme_id=|item_ids=)(\d{15,})")


async def resolve_link(text: str, timeout: float = 10) -> tuple[str, str]:
    """把用户贴的抖音链接解析成 (kind, native)：creator=主页（sec_uid）、post=作品（aweme_id）；认不出返回 ("", "")。
    支持 v.douyin.com 分享短链（跟随跳转到 iesdouyin.com/share/...）。"""
    from urllib.parse import unquote

    m = re.search(r"https?://\S+", text or "")
    if not m:
        return "", ""
    url = m.group(0)
    if "v.douyin.com" in url or "iesdouyin.com" in url:
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers={"User-Agent": UA}) as c:
                r = await c.get(url)
            url = " ".join([str(h.headers.get("location", "")) for h in r.history] + [str(r.url)])
        except httpx.HTTPError as e:
            raise RuntimeError(f"抖音短链打不开：{e}") from e
    url = unquote(url).replace("iesdouyin.com", "douyin.com")
    if u := _USER.search(url):
        return "creator", u.group(1)
    if i := _ITEM.search(url):
        return "post", i.group(1)
    return "", ""
