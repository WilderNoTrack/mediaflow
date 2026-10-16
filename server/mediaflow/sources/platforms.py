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
            return _prefer_keyword(await self._hot(c), keyword, limit)

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

    async def _hot(self, c: httpx.AsyncClient) -> list[TrendItem]:
        r = await c.get(
            "https://weibo.com/ajax/side/hotSearch",
            headers={"User-Agent": MOBILE_UA, "Referer": "https://weibo.com/"},
        )
        r.raise_for_status()
        return [
            TrendItem(title=it["note"], source=self.name, heat=str(it.get("num", "")),
                      url=f"https://s.weibo.com/weibo?q=%23{quote(it['note'])}%23")
            for it in r.json().get("data", {}).get("realtime", [])
            if it.get("note") and not it.get("is_ad")
        ]


class BaiduSource:
    """百度热搜榜。

    v1 用的是百度网页搜索，云服务器 IP 基本必弹人机验证；改用热搜榜页面里内嵌的
    s-data JSON（做法参考 imsyy/DailyHotApi），不需要登录也不触发验证。
    有关键词时只保留标题/描述里命中关键词的条目，命中太少则返回整榜给模型挑。
    """

    name, label = "baidu", "百度"
    _SDATA = re.compile(r"<!--s-data:(.*?)-->", re.S)

    async def fetch(self, keyword: str, limit: int) -> list[TrendItem]:
        import json

        async with httpx.AsyncClient(timeout=get_settings().source_timeout) as c:
            r = await c.get(
                "https://top.baidu.com/board",
                params={"tab": "realtime"},
                headers={"User-Agent": DESKTOP_UA, "Accept-Language": "zh-CN,zh;q=0.9"},
            )
        r.raise_for_status()
        m = self._SDATA.search(r.text)
        if not m:
            raise RuntimeError("百度热搜页面结构变了，没找到数据")
        data = json.loads(m.group(1))
        cards = (data.get("data") or data).get("cards") or [{}]
        content = cards[0].get("content") or []
        if content and isinstance(content[0].get("content"), list):
            content = content[0]["content"]
        items = []
        for it in content:
            t = (it.get("word") or it.get("query") or "").strip()
            if not t:
                continue
            items.append(TrendItem(
                title=t, source=self.name, heat=str(it.get("hotScore", "")),
                url=f"https://www.baidu.com/s?wd={quote(it.get('query') or t)}",
                snippet=(it.get("desc") or "")[:200],
            ))
        return _prefer_keyword(items, keyword, limit)


def _prefer_keyword(items: list[TrendItem], keyword: str, limit: int) -> list[TrendItem]:
    """热榜类来源：关键词命中的排前面；命中不足时用整榜补齐，交给模型判断相关性。"""
    if not keyword:
        return items[:limit]
    words = [w for w in re.split(r"[\s,，、]+", keyword) if w]
    hit = [i for i in items if any(w in i.title or w in i.snippet for w in words)]
    rest = [i for i in items if i not in hit]
    return (hit + rest)[:limit]


class ToutiaoSource:
    """今日头条热榜（无需登录，参考 imsyy/DailyHotApi）。"""

    name, label = "toutiao", "头条"

    async def fetch(self, keyword: str, limit: int) -> list[TrendItem]:
        async with httpx.AsyncClient(timeout=get_settings().source_timeout) as c:
            r = await c.get(
                "https://www.toutiao.com/hot-event/hot-board/",
                params={"origin": "toutiao_pc"},
                headers={"User-Agent": DESKTOP_UA},
            )
        r.raise_for_status()
        items = [
            TrendItem(title=it["Title"], source=self.name, heat=str(it.get("HotValue", "")), url=it.get("Url", ""))
            for it in r.json().get("data", []) if it.get("Title")
        ]
        return _prefer_keyword(items, keyword, limit)


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

    _buvid: tuple[dict[str, str], float] = ({}, 0.0)

    async def _ensure_buvid(self, c: httpx.AsyncClient) -> None:
        """没有 buvid3 cookie 时搜索接口会返回 code=0 但结果为空（B站风控）。

        做法参考 SocialSisterYi/bilibili-API-collect：先从 finger/spi 领一个游客 buvid。
        """
        ck, exp = BilibiliSource._buvid
        if not ck or exp < time.time():
            d = (await c.get("https://api.bilibili.com/x/frontend/finger/spi")).json().get("data") or {}
            ck = {"buvid3": d.get("b_3", ""), "buvid4": d.get("b_4", "")}
            BilibiliSource._buvid = (ck, time.time() + 3600)
        for k, v in ck.items():
            if v:
                c.cookies.set(k, v, domain=".bilibili.com")

    async def fetch(self, keyword: str, limit: int) -> list[TrendItem]:
        async with httpx.AsyncClient(
            timeout=get_settings().source_timeout,
            headers={"User-Agent": DESKTOP_UA, "Referer": "https://www.bilibili.com"},
        ) as c:
            await self._ensure_buvid(c)  # 排行榜和搜索都要游客 buvid，否则 -352
            if not keyword:
                return await self._ranking(c, limit)
            mk = await self._mixin_key(c)
            params = {"search_type": "video", "keyword": keyword, "order": "click",
                      "page": 1, "wts": int(time.time())}
            qs = "&".join(f"{k}={quote(str(v), safe='')}" for k, v in sorted(params.items()))
            params["w_rid"] = hashlib.md5((qs + mk).encode()).hexdigest()
            r = await c.get("https://api.bilibili.com/x/web-interface/wbi/search/type", params=params)
            r.raise_for_status()
            if not (r.json().get("data") or {}).get("result"):
                return await self._ranking(c, limit)  # 搜索被风控时退回排行榜
        out = []
        for it in (r.json().get("data") or {}).get("result", [])[:limit]:
            t = html.unescape(_TAG.sub("", it.get("title", "")))
            if t:
                out.append(TrendItem(
                    title=t, source=self.name, heat=str(it.get("play", "")),
                    url=f"https://www.bilibili.com/video/{it.get('bvid', '')}",
                ))
        return out

    async def _ranking(self, c: httpx.AsyncClient, limit: int) -> list[TrendItem]:
        """没有关键词时用全站排行榜。"""
        r = await c.get("https://api.bilibili.com/x/web-interface/ranking/v2", params={"rid": 0, "type": "all"})
        r.raise_for_status()
        if r.json().get("code") not in (0, None):
            raise RuntimeError(f"B站排行榜被风控（code={r.json().get('code')}）")
        return [
            TrendItem(title=it["title"], source=self.name, heat=str((it.get("stat") or {}).get("view", "")),
                      url=f"https://www.bilibili.com/video/{it.get('bvid', '')}")
            for it in (r.json().get("data") or {}).get("list", [])[:limit] if it.get("title")
        ]


class DouyinHotSource:
    name, label = "douyin", "抖音热榜"

    async def fetch(self, keyword: str, limit: int) -> list[TrendItem]:
        async with httpx.AsyncClient(timeout=get_settings().source_timeout) as c:
            r = await c.get(
                "https://www.iesdouyin.com/web/api/v2/hotsearch/billboard/word/",
                headers={"User-Agent": MOBILE_UA, "Referer": "https://www.douyin.com/"},
            )
        r.raise_for_status()
        items = [
            TrendItem(title=it["word"], source=self.name, heat=str(it.get("hot_value", "")),
                      url=f"https://www.douyin.com/search/{quote(it['word'])}")
            for it in r.json().get("word_list", []) if it.get("word")
        ]
        return _prefer_keyword(items, keyword, limit)


ALL_SOURCES = [WeiboSource(), BaiduSource(), BilibiliSource(), DouyinHotSource(), ToutiaoSource()]
