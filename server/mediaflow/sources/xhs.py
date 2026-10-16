"""小红书：扫码登录 + 关键词搜索笔记。

签名（x-s / x-s-common / x-rap-param）用 Cloxl/xhshow（MIT）。搜索接口必须是真实登录态，
游客会话会返回「没有权限访问」，所以在设置里扫码登录一次，Cookie 存进 credentials（xhs_cookie）。
建议用小号扫码：小红书风控较严，主号频繁搜索可能被限流。
"""

from __future__ import annotations

import json
import time

import httpx

from mediaflow import credentials
from mediaflow.sources.base import DESKTOP_UA, TrendItem

EDITH = "https://edith.xiaohongshu.com"
_HEADERS = {"User-Agent": DESKTOP_UA, "Origin": "https://www.xiaohongshu.com",
            "Referer": "https://www.xiaohongshu.com/", "Accept": "application/json, text/plain, */*"}
_KEEP = ("a1", "webId", "web_session", "gid", "acw_tc", "websectiga", "sec_poison_id", "xsecappid")
_pending: dict[str, dict] = {}  # qr_id -> {code, cookies, ts}；扫码过程中的游客会话
_POLL = {0: "waiting", 1: "scanned", 2: "ok", 3: "expired"}


def _parse(cookie: str) -> dict[str, str]:
    return dict(p.strip().split("=", 1) for p in cookie.split(";") if "=" in p)


def _cookie_header(cookies: dict[str, str]) -> str:
    return "; ".join(f"{k}={v}" for k, v in cookies.items())


def _signer():
    from xhshow import Xhshow
    return Xhshow()


async def _post(c: httpx.AsyncClient, path: str, payload: dict, cookies: dict, *, x_rap: bool = False):
    x = _signer()
    h = x.sign_headers_post(uri=EDITH + path, cookies=cookies, payload=payload, x_rap=x_rap)
    h["Content-Type"] = "application/json;charset=UTF-8"
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()
    h["Cookie"] = _cookie_header(cookies)
    r = await c.post(EDITH + path, content=body, headers=h)
    cookies.update({k: v for k, v in r.cookies.items()})
    return r


async def _get(c: httpx.AsyncClient, path: str, params: dict, cookies: dict):
    h = _signer().sign_headers_get(uri=EDITH + path, cookies=cookies, params=params)
    h["Cookie"] = _cookie_header(cookies)
    r = await c.get(EDITH + path, params=params, headers=h)
    cookies.update({k: v for k, v in r.cookies.items()})
    return r


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


async def qr_poll(key: str) -> dict:
    """返回 {status: waiting|scanned|expired|ok|error, message}；ok 时已把 Cookie 存好。"""
    st = _pending.get(key)
    if not st:
        return {"status": "expired", "message": "二维码已过期，请刷新"}
    cookies = st["cookies"]
    async with httpx.AsyncClient(timeout=10, headers=_HEADERS) as c:
        r = await _get(c, "/api/sns/web/v1/login/qrcode/status", {"qr_id": key, "code": st["code"]}, cookies)
    body = r.json()
    d = body.get("data") or {}
    status = _POLL.get(d.get("code_status"), "error") if body.get("success") else "error"
    if status == "ok":
        info = d.get("login_info") or {}
        if info.get("session"):
            cookies["web_session"] = info["session"]
        credentials.update({"xhs_cookie": "; ".join(f"{k}={v}" for k, v in cookies.items() if k in _KEEP)})
        _pending.pop(key, None)
    elif status == "expired":
        _pending.pop(key, None)
    return {"status": status, "message": "" if status != "error" else str(body.get("msg") or "")}


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
                             snippet=f"作者：{(card.get('user') or {}).get('nickname', '')}"))
    return out[:limit]
