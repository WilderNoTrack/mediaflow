"""B站扫码登录 + Cookie 自动续期，让 B站登录态长期有效。

流程参考 SocialSisterYi/bilibili-API-collect 的 docs/login（镜像 pskdje/bilibili-API-collect）：
- 扫码：web/qrcode/generate 拿二维码 → web/qrcode/poll 轮询，成功时下发 Cookie 和 refresh_token
- 续期：web/cookie/info 判断是否需要刷新 → 用公钥 RSA-OAEP 加密 refresh_{毫秒时间戳} 得到
  correspondPath → 访问 /correspond/1/{path} 取 refresh_csrf → web/cookie/refresh 换新 Cookie
  → web/confirm/refresh 让旧 refresh_token 失效
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import time

import httpx

from mediaflow import credentials
from mediaflow.sources.base import DESKTOP_UA

logger = logging.getLogger(__name__)

PASSPORT = "https://passport.bilibili.com/x/passport-login/web"
_HEADERS = {"User-Agent": DESKTOP_UA, "Referer": "https://www.bilibili.com/"}
_KEEP = ("SESSDATA", "bili_jct", "DedeUserID", "DedeUserID__ckMd5", "sid", "buvid3", "buvid4", "b_nut")

# 官方网页里的 RSA 公钥（1024 位，e=65537），见文档「生成CorrespondPath算法」
_N = int(
    "CB81DD8E02470656DA04DD38544446E2A3412051CFE9ADC6A330A5EF90228509684960970B91C3360CA29C49E1690FF8FA"
    "068CB9DFC6179D1E9585CB9424E847DB1EF59F33E37DD4DCA8CCFB7631EE9B4A92640D00C8204300152A0AB7CD802889D3"
    "445AEC69918FE6022B534912E7B095BE3424DAD1BA81145E969B533181F1", 16)
_E = 65537


def _mgf1(seed: bytes, length: int) -> bytes:
    out, i = b"", 0
    while len(out) < length:
        out += hashlib.sha256(seed + i.to_bytes(4, "big")).digest()
        i += 1
    return out[:length]


def rsa_oaep_sha256(message: bytes, n: int = _N, e: int = _E, seed: bytes | None = None) -> bytes:
    """RFC 8017 RSAES-OAEP（SHA-256 / MGF1-SHA-256，空 label）。纯 Python，免装加密库。"""
    k, h = (n.bit_length() + 7) // 8, 32
    if len(message) > k - 2 * h - 2:
        raise ValueError("message too long")
    db = hashlib.sha256(b"").digest() + b"\x00" * (k - len(message) - 2 * h - 2) + b"\x01" + message
    seed = seed or os.urandom(h)
    masked_db = bytes(a ^ b for a, b in zip(db, _mgf1(seed, k - h - 1)))
    masked_seed = bytes(a ^ b for a, b in zip(seed, _mgf1(masked_db, h)))
    em = b"\x00" + masked_seed + masked_db
    return pow(int.from_bytes(em, "big"), e, n).to_bytes(k, "big")


def correspond_path(ts_ms: int | None = None) -> str:
    ts_ms = ts_ms or int(time.time() * 1000)
    return rsa_oaep_sha256(f"refresh_{ts_ms}".encode()).hex()


def _cookie_str(jar: dict[str, str]) -> str:
    return "; ".join(f"{k}={v}" for k, v in jar.items() if v)


def _parse(raw: str) -> dict[str, str]:
    out = {}
    for part in raw.split(";"):
        k, sep, v = part.strip().partition("=")
        if sep and k:
            out[k] = v
    return out


def _save(jar: dict[str, str], refresh_token: str) -> None:
    keep = {k: v for k, v in jar.items() if k in _KEEP and v}
    credentials.update({"bilibili_cookie": _cookie_str(keep), "bilibili_refresh_token": refresh_token,
                        "bilibili_refreshed_at": str(int(time.time()))})


async def qr_generate() -> dict:
    async with httpx.AsyncClient(timeout=10, headers=_HEADERS) as c:
        d = (await c.get(f"{PASSPORT}/qrcode/generate")).json()["data"]
    return {"url": d["url"], "key": d["qrcode_key"]}


_POLL = {86101: "waiting", 86090: "scanned", 86038: "expired", 0: "ok"}


async def qr_poll(key: str) -> dict:
    """返回 {status: waiting|scanned|expired|ok|error, message}；ok 时已把 Cookie 存好。"""
    async with httpx.AsyncClient(timeout=10, headers=_HEADERS) as c:
        r = await c.get(f"{PASSPORT}/qrcode/poll", params={"qrcode_key": key})
        d = r.json().get("data") or {}
        status = _POLL.get(d.get("code"), "error")
        if status == "ok":
            jar = {k: v for k, v in c.cookies.items()}
            if "SESSDATA" not in jar:  # 少数情况下只在跨域 url 里给
                jar.update(dict(re.findall(r"(\w+)=([^&]+)", d.get("url", ""))))
            _save(jar, d.get("refresh_token", ""))
    return {"status": status, "message": d.get("message", "")}


async def refresh_if_needed(force: bool = False) -> str:
    """检查并刷新 B站 Cookie。返回 skipped / fresh / refreshed / no_token / failed:原因。"""
    cookie, token = credentials.get("bilibili_cookie"), credentials.get("bilibili_refresh_token")
    if not cookie:
        return "skipped"
    if not token:
        return "no_token"
    jar = _parse(cookie)
    async with httpx.AsyncClient(timeout=15, headers=_HEADERS) as c:
        c.cookies.update(jar)
        info = (await c.get(f"{PASSPORT}/cookie/info", params={"csrf": jar.get("bili_jct", "")})).json()
        if info.get("code") == -101:
            return "failed:登录已失效，需要重新扫码"
        if not force and not (info.get("data") or {}).get("refresh"):
            credentials.update({"bilibili_refreshed_at": str(int(time.time()))})
            return "fresh"
        ts = (info.get("data") or {}).get("timestamp") or int(time.time() * 1000)
        page = await c.get(f"https://www.bilibili.com/correspond/1/{correspond_path(ts)}")
        m = re.search(r'<div id="1-name">([^<]+)</div>', page.text)
        if not m:
            return "failed:拿不到 refresh_csrf"
        r = await c.post(f"{PASSPORT}/cookie/refresh", data={
            "csrf": jar.get("bili_jct", ""), "refresh_csrf": m.group(1).strip(),
            "source": "main_web", "refresh_token": token})
        body = r.json()
        if body.get("code") != 0:
            return f"failed:{body.get('message') or body.get('code')}"
        new_jar = {**jar, **{k: v for k, v in r.cookies.items()}}
        new_token = (body.get("data") or {}).get("refresh_token", "")
        await c.post(f"{PASSPORT}/confirm/refresh", data={"csrf": new_jar.get("bili_jct", ""), "refresh_token": token},
                     cookies=new_jar)
    _save(new_jar, new_token)
    return "refreshed"


async def daily_refresh() -> None:
    """调度器每轮调用；一天最多真正检查一次。"""
    last = credentials.get("bilibili_refreshed_at")
    if last and time.time() - float(last) < 86400:
        return
    try:
        res = await refresh_if_needed()
        logger.info("B站 Cookie 续期检查：%s", res)
    except Exception as e:  # noqa: BLE001
        logger.warning("B站 Cookie 续期失败：%s", e)
