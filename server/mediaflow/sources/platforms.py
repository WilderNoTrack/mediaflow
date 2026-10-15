"""各平台抓取实现（从 v1 移植并改为 async）。

抖音关键词搜索、小红书搜索需要签名或登录态，v1 里也经常失效，第一期先不接，
只保留稳定可用的来源。新增来源：写一个类，加进 ALL_SOURCES。
"""

from __future__ import annotations

import hashlib
import html
import re
import time
from urllib.parse import quote

import httpx

from mediaflow.config import get_settings
from mediaflow.sources.base import DESKTOP_UA, MOBILE_UA, TrendItem

_TAG = re.compile(r"<[^>]+>")


class WeiboSource:
    name, label = "weibo", "微博"

    async def fetch(self, keyword: str, limit: int) -> list[TrendItem]:
        s = get_settings()
        async with httpx.AsyncClient(timeout=s.source_timeout, follow_redirects=False) as c:
            if s.weibo_cookie and keyword:
                items = await self._search(c, keyword, limit, s.weibo_cookie)
                if items:
                    return items
            return await self._hot(c, limit)

    async def _search(self, c: httpx.AsyncClient, kw: str, limit: int, cookie: str) -> list[TrendItem]:
        from bs4 import BeautifulSoup

        r = await c.get(
            "https://s.weibo.com/weibo",
            params={"q": kw},
            headers={"User-Agent": DESKTOP_UA, "Referer": "https://weibo.com/", "Cookie": cookie},
        )
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        out = []
        for card in soup.select("div.card-wrap[mid]")[:limit]:
            el = card.select_one("p.txt")
            if not el:
                continue
            text = re.sub(r"\s*全文\s*$", "", el.get_text(" ", strip=True)).strip()
            if text:
                out.append(TrendItem(title=text[:80], source=self.name))
        return out

    async def _hot(self, c: httpx.AsyncClient, limit: int) -> list[TrendItem]:
        r = await c.get(
            "https://weibo.com/ajax/side/hotSearch",
            headers={"User-Agent": MOBILE_UA, "Referer": "https://weibo.com/"},
        )
        r.raise_for_status()
        out = []
        for it in r.json().get("data", {}).get("realtime", []):
            if it.get("is_ad") or not it.get("note"):
                continue
            t = it["note"]
            out.append(TrendItem(
                title=t, source=self.name, heat=str(it.get("num", "")),
                url=f"https://s.weibo.com/weibo?q=%23{quote(t)}%23",
            ))
            if len(out) >= limit:
                break
        return out


class BaiduSource:
    name, label = "baidu", "百度"

    async def fetch(self, keyword: str, limit: int) -> list[TrendItem]:
        from bs4 import BeautifulSoup

        if not keyword:
            return []
        async with httpx.AsyncClient(timeout=get_settings().source_timeout) as c:
            r = await c.get(
                "https://www.baidu.com/s",
                params={"ie": "utf-8", "wd": keyword},
                headers={"User-Agent": DESKTOP_UA, "Accept-Language": "zh-CN,zh;q=0.9"},
            )
        if r.is_redirect and "captcha" in r.headers.get("location", ""):
            raise RuntimeError("百度要求人机验证，暂时抓不了")
        r.raise_for_status()
        skip = ("淘宝", "京东", "拼多多", "广告", "百度百科", "百度知道", "天猫")
        soup = BeautifulSoup(r.text, "html.parser")
        out: list[TrendItem] = []
        seen: set[str] = set()
        for box in soup.select(".result, .c-container"):
            a = box.select_one("h3 a")
            if not a:
                continue
            t = html.unescape(re.sub(r"\s+", " ", a.get_text())).strip(" -—·")
            if len(t) < 6 or t in seen or any(k in t for k in skip):
                continue
            seen.add(t)
            ab = box.select_one(".c-abstract, [class*='abstract']")
            out.append(TrendItem(
                title=t, source=self.name, url=a.get("href", ""),
                snippet=ab.get_text(strip=True)[:200] if ab else "",
            ))
            if len(out) >= limit:
                break
        return out


_WBI_ENC = [46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
            33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13]


class BilibiliSource:
    name, label = "bilibili", "B站"
    _key: tuple[str, float] = ("", 0.0)

    async def _mixin_key(self, c: httpx.AsyncClient) -> str:
        key, exp = BilibiliSource._key
        if key and exp > time.time():
            return key
        r = await c.get("https://api.bilibili.com/x/web-interface/nav")
        wbi = r.json()["data"]["wbi_img"]
        raw = wbi["img_url"].rsplit("/", 1)[1].split(".")[0] + wbi["sub_url"].rsplit("/", 1)[1].split(".")[0]
        key = "".join(raw[i] for i in _WBI_ENC)[:32]
        BilibiliSource._key = (key, time.time() + 300)
        return key

    async def fetch(self, keyword: str, limit: int) -> list[TrendItem]:
        if not keyword:
            return []
        async with httpx.AsyncClient(
            timeout=get_settings().source_timeout,
            headers={"User-Agent": DESKTOP_UA, "Referer": "https://www.bilibili.com"},
        ) as c:
            mk = await self._mixin_key(c)
            params = {"search_type": "video", "keyword": keyword, "order": "click",
                      "page": 1, "wts": int(time.time())}
            qs = "&".join(f"{k}={quote(str(v), safe='')}" for k, v in sorted(params.items()))
            params["w_rid"] = hashlib.md5((qs + mk).encode()).hexdigest()
            r = await c.get("https://api.bilibili.com/x/web-interface/wbi/search/type", params=params)
        r.raise_for_status()
        out = []
        for it in (r.json().get("data") or {}).get("result", [])[:limit]:
            t = html.unescape(_TAG.sub("", it.get("title", "")))
            if t:
                out.append(TrendItem(
                    title=t, source=self.name, heat=str(it.get("play", "")),
                    url=f"https://www.bilibili.com/video/{it.get('bvid', '')}",
                ))
        return out


class DouyinHotSource:
    name, label = "douyin", "抖音热榜"

    async def fetch(self, keyword: str, limit: int) -> list[TrendItem]:
        async with httpx.AsyncClient(timeout=get_settings().source_timeout) as c:
            r = await c.get(
                "https://www.iesdouyin.com/web/api/v2/hotsearch/billboard/word/",
                headers={"User-Agent": MOBILE_UA, "Referer": "https://www.douyin.com/"},
            )
        r.raise_for_status()
        out = []
        for it in r.json().get("word_list", [])[:limit]:
            w = it.get("word")
            if w:
                out.append(TrendItem(
                    title=w, source=self.name, heat=str(it.get("hot_value", "")),
                    url=f"https://www.douyin.com/search/{quote(w)}",
                ))
        return out


ALL_SOURCES = [WeiboSource(), BaiduSource(), BilibiliSource(), DouyinHotSource()]
