"""小红书：扫码登录 + 关键词搜索笔记。

签名（x-s / x-s-common / x-rap-param）用 Cloxl/xhshow（MIT）。搜索接口必须是真实登录态，
游客会话会返回「没有权限访问」，所以在设置里扫码登录一次，Cookie 存进 credentials（xhs_cookie）。
建议用小号扫码：小红书风控较严，主号频繁搜索可能被限流。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time

import httpx

from mediaflow import credentials
from mediaflow.sources.base import DESKTOP_UA, TrendItem

logger = logging.getLogger(__name__)
EDITH = "https://edith.xiaohongshu.com"
_HEADERS = {"User-Agent": DESKTOP_UA, "Origin": "https://www.xiaohongshu.com",
            "Referer": "https://www.xiaohongshu.com/", "Accept": "application/json, text/plain, */*"}
_KEEP = ("a1", "webId", "web_session", "web_session_sec", "gid", "acw_tc", "websectiga", "sec_poison_id", "xsecappid")
_pending: dict[str, dict] = {}  # qr_id -> {code, cookies, ts}；扫码过程中的游客会话
_POLL = {0: "waiting", 1: "scanned", 2: "ok", 3: "expired"}


def _parse(cookie: str) -> dict[str, str]:
    return dict(p.strip().split("=", 1) for p in cookie.split(";") if "=" in p)


def _cookie_header(cookies: dict[str, str]) -> str:
    return "; ".join(f"{k}={v}" for k, v in cookies.items())


def _signer():
    from xhshow import Xhshow
    return Xhshow()


async def _post(c: httpx.AsyncClient, path: str, payload: dict, cookies: dict, *, x_rap: bool = False,
                extra: dict | None = None):
    x = _signer()
    h = x.sign_headers_post(uri=EDITH + path, cookies=cookies, payload=payload, x_rap=x_rap)
    h["Content-Type"] = "application/json;charset=UTF-8"
    h.update(extra or {})
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()
    h["Cookie"] = _cookie_header(cookies)
    r = await c.post(EDITH + path, content=body, headers=h)
    cookies.update({k: v for k, v in r.cookies.items()})
    return r


async def _get(c: httpx.AsyncClient, path: str, params: dict, cookies: dict, *, x_rap: bool = False,
               extra: dict | None = None):
    x = _signer()
    h = x.sign_headers_get(uri=EDITH + path, cookies=cookies, params=params, x_rap=x_rap)
    h.update(extra or {})
    h["Cookie"] = _cookie_header(cookies)
    # 查询串必须和签名时完全一致（逗号等字符的编码方式），所以用签名库自己拼 URL
    url = x.build_url(base_url=EDITH + path, params=params) if params else EDITH + path
    r = await c.get(url, headers=h)
    cookies.update({k: v for k, v in r.cookies.items()})
    return r


async def _me(c: httpx.AsyncClient, cookies: dict) -> dict:
    try:
        return (await _get(c, "/api/sns/web/v2/user/me", {}, cookies)).json().get("data") or {}
    except ValueError:
        return {}


async def qr_create() -> dict:
    """生成登录二维码，返回 {url, key}；key 就是 qr_id。"""
    from xhshow import Xhshow

    a1 = Xhshow.generate_a1()
    cookies = {"a1": a1, "webId": Xhshow.generate_web_id(a1)}
    async with httpx.AsyncClient(timeout=15, headers=_HEADERS) as c:
        await _post(c, "/api/sns/web/v1/login/activate", {}, cookies)  # 先拿游客 web_session
        d = ((await _post(c, "/api/sns/web/v1/login/qrcode/create", {"qr_type": 1}, cookies)).json()
             .get("data") or {})
    if not d.get("qr_id"):
        raise RuntimeError("小红书没有返回二维码，稍后再试")
    now = time.time()
    for k in [k for k, v in _pending.items() if now - v["ts"] > 600]:
        _pending.pop(k, None)
    _pending[d["qr_id"]] = {"code": d["code"], "cookies": cookies, "ts": now}
    return {"url": d["url"], "key": d["qr_id"]}


_RISK = ("小红书要求做一次人机验证才能登录（常见于新设备/主号）。可以换个小号再扫，"
         "或者在电脑浏览器登录小红书网页版后，把 Cookie 粘贴到下面")


async def qr_poll(key: str) -> dict:
    """返回 {status: waiting|scanned|expired|ok|error, message}；ok 时已把 Cookie 存好。

    流程和小红书网页版一致：先用 /api/qrcode/userinfo 轮询扫码状态（codeStatus 0 等待 / 1 已扫 / 2 已确认 / 3 过期），
    确认后调 login/qrcode/status（带 x-login-mode: qrcode）换出正式 web_session（可能要重试几次），最后用 user/me 核对。
    偶发的网络或接口错误不直接判失败，连续多次才报错，免得用户刚扫完就被打断。
    """
    st = _pending.get(key)
    if not st:
        return {"status": "expired", "message": "二维码已过期，请刷新"}
    cookies = st["cookies"]
    async with httpx.AsyncClient(timeout=10, headers=_HEADERS) as c:
        try:
            r = await _post(c, "/api/qrcode/userinfo", {"qrId": key, "code": st["code"]}, cookies,
                            extra={"service-tag": "webcn"})
            body = r.json()
        except (httpx.HTTPError, ValueError) as e:
            body = {"success": False, "msg": f"网络错误：{e}"}
        d = body.get("data") or {}
        if not body.get("success"):
            st["fails"] = st.get("fails", 0) + 1
            logger.warning("小红书扫码状态查询失败（第 %s 次）：%s", st["fails"], str(body)[:300])
            if st["fails"] < 5:
                return {"status": st.get("last", "waiting"), "message": ""}
            _pending.pop(key, None)
            return {"status": "error", "message": f"查不到扫码状态：{body.get('msg') or body.get('code') or '未知错误'}"}
        st["fails"] = 0
        try:
            code = int(d.get("codeStatus", d.get("code_status", -1)))
        except (TypeError, ValueError):
            code = -1
        status = _POLL.get(code, "waiting")
        if status != "ok":
            st["last"] = status
            if status == "expired":
                _pending.pop(key, None)
            return {"status": status, "message": ""}

        want = str(d.get("userId") or "")
        session = ""
        last = ""
        for _ in range(5):
            try:
                done = await _get(c, "/api/sns/web/v1/login/qrcode/status", {"qr_id": key, "code": st["code"]},
                                  cookies, extra={"x-login-mode": "qrcode"})
            except httpx.HTTPError as e:
                last = f"网络错误：{e}"
                await asyncio.sleep(1)
                continue
            if done.status_code in (461, 471):
                logger.warning("小红书扫码确认后触发风控：HTTP %s %s", done.status_code, dict(done.headers))
                _pending.pop(key, None)
                return {"status": "error", "message": _RISK}
            try:
                res = done.json()
            except ValueError:
                res = {}
            info = (res.get("data") or {}).get("login_info") or {}
            if not res.get("success", True):
                last = str(res.get("msg") or res.get("code") or "")
            if info.get("session"):
                session = cookies["web_session"] = info["session"]
            if info.get("secure_session"):
                cookies["web_session_sec"] = info["secure_session"]
            me = await _me(c, cookies)
            if me.get("user_id") and not me.get("guest") and (not want or me["user_id"] == want):
                break
            if session and not me:
                logger.warning("小红书扫码登录：拿到了 session 但 user/me 没返回，按登录成功处理")
                break
            logger.info("小红书扫码登录：还没换到登录态 %s / me=%s", str(res)[:300], str(me)[:200])
            await asyncio.sleep(1)
        else:
            _pending.pop(key, None)
            hint = f"（小红书返回：{last}）" if last else ""
            return {"status": "error", "message": f"手机上已确认，但没换到登录态{hint}，刷新二维码再扫一次；还不行就粘贴 Cookie"}
    credentials.update({"xhs_cookie": "; ".join(f"{k}={v}" for k, v in cookies.items() if k in _KEEP)})
    _pending.pop(key, None)
    return {"status": "ok", "message": ""}


async def search(keyword: str, limit: int, cookie: str, timeout: float = 10) -> list[TrendItem]:
    x = _signer()
    cookies = _parse(cookie)
    payload = {"keyword": keyword, "page": 1, "page_size": 20, "search_id": x.get_search_id(),
               "sort": "general", "note_type": 0, "ext_flags": [], "geo": "",
               "image_formats": ["jpg", "webp", "avif"]}
    async with httpx.AsyncClient(timeout=timeout, headers=_HEADERS) as c:
        r = await _post(c, "/api/sns/web/v1/search/notes", payload, cookies, x_rap=True)
    if r.status_code in (461, 471):
        raise RuntimeError("小红书触发了验证码风控，稍后再试或重新扫码登录")
    body = r.json()
    if not body.get("success"):
        msg = body.get("msg") or body.get("code")
        if body.get("code") in (-100, -101, -104):
            raise RuntimeError(f"小红书：{msg}（登录可能失效，请重新扫码）")
        raise RuntimeError(f"小红书：{msg}")
    out = []
    for it in (body.get("data") or {}).get("items") or []:
        card = it.get("note_card") or {}
        title = " ".join((card.get("display_title") or "").split())
        if it.get("model_type") != "note" or not title or not it.get("id"):
            continue
        liked = (card.get("interact_info") or {}).get("liked_count", "")
        url = f"https://www.xiaohongshu.com/explore/{it['id']}"
        if it.get("xsec_token"):
            url += f"?xsec_token={it['xsec_token']}&xsec_source=pc_search"
        out.append(TrendItem(title=title[:80], source="xiaohongshu", url=url,
                             heat=f"{liked}赞" if liked else "",
                             snippet=f"作者：{(card.get('user') or {}).get('nickname', '')}",
                             ref=f"{it['id']}|{it.get('xsec_token', '')}"))
    return out[:limit]


# ── 调研能力：搜博主 / 博主作品 / 笔记详情 ─────────────────────────────


def _cover(card: dict) -> str:
    c = card.get("cover") or {}
    url = c.get("url_default") or c.get("url_pre") or c.get("url") or ""
    if not url:
        for i in c.get("info_list") or []:
            url = i.get("url") or url
    return url.replace("http://", "https://", 1)


def _img_url(img: dict) -> str:
    """详情里一张图的地址：优先 url_default，其次 info_list 里的第一张。"""
    if not isinstance(img, dict):
        return ""
    u = img.get("url_default") or img.get("url") or next((i.get("url") for i in img.get("info_list") or [] if i.get("url")), "")
    return u.replace("http://", "https://", 1) if u else ""


def _need_cookie() -> dict[str, str]:
    from mediaflow.research.types import Unsupported

    cookie = credentials.get("xhs_cookie")
    if not cookie:
        raise Unsupported("小红书没登录，请先在「数据来源」里扫码或粘贴 Cookie")
    return _parse(cookie)


def _check(body: dict, what: str) -> dict:
    if not body.get("success"):
        msg = body.get("msg") or body.get("code")
        hint = "（登录可能失效，请重新扫码）" if body.get("code") in (-100, -101, -104) else ""
        raise RuntimeError(f"小红书{what}失败：{msg}{hint}")
    return body.get("data") or {}


NOTE_TYPE_IMAGE = 2  # 小红书搜索筛选：0 不限 / 1 视频 / 2 图文


async def search_hot_authors(keyword: str, timeout: float = 15, *, note_type: int = NOTE_TYPE_IMAGE) -> list[dict]:
    """按关键词搜最热的笔记，带出作者（找同领域对标账号用）。默认只搜图文笔记——我们做的是图文号。"""
    cookies, x = _need_cookie(), _signer()
    payload = {"keyword": keyword, "page": 1, "page_size": 20, "search_id": x.get_search_id(),
               "sort": "popularity_descending", "note_type": note_type, "ext_flags": [], "geo": "",
               "image_formats": ["jpg", "webp", "avif"]}
    async with httpx.AsyncClient(timeout=timeout, headers=_HEADERS) as c:
        r = await _post(c, "/api/sns/web/v1/search/notes", payload, cookies, x_rap=True)
    if r.status_code in (461, 471):
        raise RuntimeError("小红书触发了验证码风控，稍后再试或重新扫码登录")
    out = []
    for it in _check(r.json(), "搜笔记").get("items") or []:
        card = it.get("note_card") or {}
        u = card.get("user") or {}
        title = " ".join((card.get("display_title") or "").split())
        if it.get("model_type") != "note" or not u.get("user_id") or not title:
            continue
        out.append({"user_id": u["user_id"], "name": u.get("nickname") or u.get("nick_name") or "",
                    "avatar": u.get("avatar", ""), "native": f"{u['user_id']}|{u.get('xsec_token', '')}",
                    "title": title[:60], "likes": str((card.get("interact_info") or {}).get("liked_count", "")),
                    "cover": _cover(card), "kind": "视频" if card.get("type") == "video" else "图文",
                    "url": f"https://www.xiaohongshu.com/explore/{it['id']}?xsec_token={it.get('xsec_token', '')}"
                           "&xsec_source=pc_search"})
    return out


async def search_creators(name: str, limit: int = 5, timeout: float = 15):
    from mediaflow.research.types import Creator

    cookies, x = _need_cookie(), _signer()
    payload = {"search_user_request": {"keyword": name, "search_id": x.get_search_id(), "page": 1,
                                       "page_size": 15, "biz_type": "web_search_user",
                                       "request_id": x.get_search_request_id()}}
    async with httpx.AsyncClient(timeout=timeout, headers=_HEADERS) as c:
        r = await _post(c, "/api/sns/web/v1/search/usersearch", payload, cookies, x_rap=True)
    out = []
    for u in _check(r.json(), "搜博主").get("users") or []:
        if not u.get("id"):
            continue
        out.append(Creator(
            platform="xiaohongshu", name=u.get("name", ""), native=f"{u['id']}|{u.get('xsec_token', '')}",
            fans=str(u.get("fans", "")), posts=str(u.get("note_count", "")), desc=u.get("sub_title", ""),
            url=f"https://www.xiaohongshu.com/user/profile/{u['id']}",
        ))
    return out[:limit]


async def creator_posts(native: str, limit: int = 10, timeout: float = 15):
    from mediaflow.research.types import Creator, Post, fmt_count, ms_date

    cookies = _need_cookie()
    uid, _, tok = native.partition("|")
    async with httpx.AsyncClient(timeout=timeout, headers=_HEADERS) as c:
        info = _check((await _get(c, "/api/sns/web/v1/user/otherinfo",
                                  {"target_user_id": uid, "xsec_token": tok, "xsec_source": "pc_search"},
                                  cookies)).json(), "看博主主页")
        notes: list[dict] = []
        cursor = ""
        for _ in range(3):  # 一页 30 条，最多翻 3 页（复刻拆解要看更多历史爆款）
            await asyncio.sleep(0.8)
            data = _check((await _get(c, "/api/sns/web/v1/user_posted",
                                      {"num": "30", "cursor": cursor, "user_id": uid, "image_scenes": "FD_WM_WEBP"},
                                      cookies)).json(), "看博主作品")
            notes += data.get("notes") or []
            nxt = data.get("cursor") or ""
            if len(notes) >= limit or not data.get("has_more") or not nxt or nxt == cursor:
                break
            cursor = nxt
    basic = info.get("basic_info") or {}
    inter = {i.get("type"): i.get("count") for i in info.get("interactions") or []}
    creator = Creator(
        platform="xiaohongshu", name=basic.get("nickname", ""), native=native,
        fans=fmt_count(inter.get("fans", "")), desc=" ".join((basic.get("desc") or "").split())[:200],
        url=f"https://www.xiaohongshu.com/user/profile/{uid}",
        extra={"avatar": basic.get("images") or basic.get("imageb") or "",
               "获赞与收藏": fmt_count((info.get("liked") or 0) + (info.get("collected") or 0)),
               "标签": [t.get("name") for t in info.get("tags") or [] if t.get("name")]},
    )
    posts, seen = [], set()
    for n in notes:
        # 翻页时小红书偶尔会把同一页再返回一次，按笔记 ID 去重
        if not n.get("note_id") or n["note_id"] in seen:
            continue
        seen.add(n["note_id"])
        posts.append(Post(
            platform="xiaohongshu", title=" ".join((n.get("display_title") or "").split()) or "（无标题）",
            native=f"{n['note_id']}|{n.get('xsec_token', '')}", author=creator.name,
            likes=str((n.get("interact_info") or {}).get("liked_count", "")),
            published=ms_date(n.get("time")), kind="视频" if n.get("type") == "video" else "图文",
            url=f"https://www.xiaohongshu.com/explore/{n['note_id']}?xsec_token={n.get('xsec_token', '')}&xsec_source=pc_user",
            cover=_cover(n),
        ))
    return creator, posts[:limit]


async def post_detail(native: str, comments: int = 8, timeout: float = 15):
    from mediaflow.research.types import PostDetail, count_num, ms_date

    cookies = _need_cookie()
    nid, _, tok = native.partition("|")
    payload = {"source_note_id": nid, "image_formats": ["jpg", "webp", "avif"],
               "extra": {"need_body_topic": "1"}, "xsec_source": "pc_search", "xsec_token": tok}
    async with httpx.AsyncClient(timeout=timeout, headers=_HEADERS) as c:
        data = _check((await _post(c, "/api/sns/web/v1/feed", payload, cookies, x_rap=True)).json(), "看笔记详情")
        items = data.get("items") or []
        if not items:
            raise RuntimeError("小红书没有返回这篇笔记（可能已删除或仅自己可见）")
        card = items[0].get("note_card") or {}
        await asyncio.sleep(0.8)
        cm = (await _get(c, "/api/sns/web/v2/comment/page",
                         {"note_id": nid, "cursor": "", "top_comment_id": "", "image_formats": "jpg,webp,avif",
                          "xsec_token": tok}, cookies)).json()
    it = card.get("interact_info") or {}
    top = sorted((cm.get("data") or {}).get("comments") or [], key=lambda x: -count_num(x.get("like_count")))
    return PostDetail(
        platform="xiaohongshu", title=card.get("title") or "（无标题）", native=native,
        url=f"https://www.xiaohongshu.com/explore/{nid}?xsec_token={tok}&xsec_source=pc_search",
        author=(card.get("user") or {}).get("nickname", ""),
        author_native=f"{(card.get('user') or {}).get('user_id', '')}|{(card.get('user') or {}).get('xsec_token', '')}"
        if (card.get("user") or {}).get("user_id") else "",
        likes=str(it.get("liked_count", "")),
        comments=str(it.get("comment_count", "")), collects=str(it.get("collected_count", "")),
        shares=str(it.get("share_count", "")), published=ms_date(card.get("time")),
        kind="视频" if card.get("type") == "video" else "图文",
        cover=_img_url(((card.get("image_list") or [{}])[0])),
        images=[u for u in (_img_url(i) for i in card.get("image_list") or []) if u][:9],
        content=(card.get("desc") or "").strip()[:1500],
        tags=[t.get("name") for t in card.get("tag_list") or [] if t.get("name")],
        top_comments=[f"{x.get('like_count', 0)}赞｜{' '.join((x.get('content') or '').split())[:120]}"
                      for x in top[:comments] if x.get("content")],
    )


_PROFILE = re.compile(r"/user/profile/([0-9a-zA-Z]{16,32})")
_NOTE = re.compile(r"/(?:explore|discovery/item)/([0-9a-zA-Z]{16,32})")
_TOKEN = re.compile(r"xsec_token=([^&#\s]+)")


async def resolve_link(text: str, timeout: float = 10) -> tuple[str, str]:
    """把用户贴的链接解析成 (kind, native)：kind 为 creator 或 post；认不出返回 ("", "")。

    支持主页链接、笔记链接、xhslink.com 短链（跟随跳转，跳到登录页时从 redirectPath 里取原地址）。
    """
    from urllib.parse import unquote

    m = re.search(r"https?://\S+", text or "")
    if not m:
        return "", ""
    url = m.group(0)
    if "xhslink.com" in url:
        try:
            async with httpx.AsyncClient(timeout=timeout, headers=_HEADERS, follow_redirects=True) as c:
                r = await c.get(url)
            url = " ".join([str(h.headers.get("location", "")) for h in r.history] + [str(r.url)])
        except httpx.HTTPError as e:
            raise RuntimeError(f"短链打不开：{e}") from e
    url = unquote(unquote(url))
    tok = _TOKEN.search(url)
    token = tok.group(1) if tok else ""
    if p := _PROFILE.search(url):
        return "creator", f"{p.group(1)}|{token}"
    if n := _NOTE.search(url):
        return "post", f"{n.group(1)}|{token}"
    return "", ""
