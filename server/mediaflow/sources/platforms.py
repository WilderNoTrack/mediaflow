"""各平台抓取实现。

优先「关键词搜索」，配了凭据才启用；没配时能退回热榜的就退回热榜（条目标 kind="hot"），
退不了的抛 NotConfigured，界面显示为「未启用」。凭据在设置里填，见 mediaflow/credentials.py。

- 知乎：知乎数据开放平台官方搜索 API（Access Secret）
- 百度：百度千帆 AI 搜索 API（官方，返回百度搜索结果）
- 小红书：网页版笔记搜索 + 扫码登录 + xhshow 签名（xhs.py）
- 抖音：网页版搜索接口 + 登录 Cookie + a_bogus 签名（douyin_abogus/）
- B站：WBI 签名搜索，游客 buvid 即可，配 Cookie 更稳
- 微博：s.weibo.com 搜索 + 登录 Cookie
- 微信文章：搜狗微信搜索，无需配置
新增来源：写一个类，加进底部的来源列表。
"""

from __future__ import annotations

import asyncio
import hashlib
import html
import re
import time
from urllib.parse import quote

import httpx

from mediaflow.config import get_settings
from mediaflow import credentials
from mediaflow.sources.base import DESKTOP_UA, MOBILE_UA, NotConfigured, TrendItem

_TAG = re.compile(r"<[^>]+>")


class WeiboSource:
    name, label = "weibo", "微博"

    async def fetch(self, keyword: str, limit: int) -> list[TrendItem]:
        cookie = credentials.get("weibo_cookie")
        async with httpx.AsyncClient(timeout=get_settings().source_timeout, follow_redirects=False) as c:
            if cookie and keyword:
                items = await self._search(c, keyword, limit, cookie)
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
            return []  # Cookie 过期会 302 到登录页，退回热榜
        soup = BeautifulSoup(r.text, "html.parser")
        out = []
        for card in soup.select("div.card-wrap[mid]")[:limit]:
            el = card.select_one("p.txt")
            if not el:
                continue
            text = re.sub(r"\s*全文\s*$", "", el.get_text(" ", strip=True)).strip()
            if text:
                link = card.select_one("div.from a[href]")
                href = link["href"] if link else ""
                out.append(TrendItem(title=text[:80], source=self.name, snippet=text[:200],
                                     url=("https:" + href) if href.startswith("//") else href))
        return out

    async def _hot(self, c: httpx.AsyncClient) -> list[TrendItem]:
        r = await c.get(
            "https://weibo.com/ajax/side/hotSearch",
            headers={"User-Agent": MOBILE_UA, "Referer": "https://weibo.com/"},
        )
        r.raise_for_status()
        return [
            TrendItem(title=it["note"], source=self.name, heat=str(it.get("num", "")), kind="hot",
                      url=f"https://s.weibo.com/weibo?q=%23{quote(it['note'])}%23")
            for it in r.json().get("data", {}).get("realtime", [])
            if it.get("note") and not it.get("is_ad")
        ]


class BaiduSource:
    """百度：配了千帆 API Key 就走官方 AI 搜索（百度搜索结果），否则退回百度热搜榜。

    百度网页搜索对非浏览器请求基本必弹人机验证，所以不直接抓 baidu.com/s。
    千帆接口参考 HKUDS/DeepTutor 的 qianfan provider；热搜榜解析参考 imsyy/DailyHotApi。
    """

    name, label = "baidu", "百度"
    _SDATA = re.compile(r"<!--s-data:(.*?)-->", re.S)
    SEARCH_URL = "https://qianfan.baidubce.com/v2/ai_search/web_search"

    async def fetch(self, keyword: str, limit: int) -> list[TrendItem]:
        key = credentials.get("qianfan_api_key")
        if key and keyword:
            return await self._search(keyword, limit, key)
        return await self._hot(keyword, limit)

    async def _search(self, keyword: str, limit: int, key: str) -> list[TrendItem]:
        async with httpx.AsyncClient(timeout=max(get_settings().source_timeout, 20)) as c:
            r = await c.post(self.SEARCH_URL, headers={"Authorization": f"Bearer {key}"}, json={
                "messages": [{"role": "user", "content": keyword[:72]}],
                "search_source": "baidu_search_v2",
                "resource_type_filter": [{"type": "web", "top_k": max(1, min(limit, 20))}],
                "search_recency_filter": "month",
            })
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        if r.status_code != 200 or data.get("code") not in (None, 0, "0"):
            raise RuntimeError(f"千帆搜索出错：{data.get('message') or r.status_code}"[:60])
        return [
            TrendItem(title=(it.get("title") or "").strip(), source=self.name, url=it.get("url", ""),
                      snippet=(it.get("snippet") or it.get("content") or "")[:200],
                      heat=it.get("date", "") or "")
            for it in data.get("references") or [] if it.get("title")
        ][:limit]

    async def _hot(self, keyword: str, limit: int) -> list[TrendItem]:
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
                title=t, source=self.name, heat=str(it.get("hotScore", "")), kind="hot",
                url=f"https://www.baidu.com/s?wd={quote(it.get('query') or t)}",
                snippet=(it.get("desc") or "")[:200],
            ))
        return _prefer_keyword(items, keyword, limit)


class ZhihuSource:
    """知乎数据开放平台官方搜索 API（developer.zhihu.com）。

    鉴权：Authorization: Bearer <Access Secret> + X-Request-Timestamp（与服务器时差需 < 10 分钟）。
    接口与错误码参考 dsh-plugin-lab/dsh-zhihu-search 的实测记录。
    """

    name, label = "zhihu", "知乎"
    URL = "https://developer.zhihu.com/api/v1/content/zhihu_search"
    _ERRORS = {20001: "Access Secret 无效，或电脑时间不准", 30001: "请求太频繁/额度用完", 10001: "参数被拒绝"}

    async def fetch(self, keyword: str, limit: int) -> list[TrendItem]:
        secret = credentials.get("zhihu_access_secret")
        if not secret:
            raise NotConfigured("没配置知乎开放平台 Access Secret")
        if not keyword:
            return []
        async with httpx.AsyncClient(timeout=get_settings().source_timeout) as c:
            for attempt in range(2):
                r = await c.get(self.URL, params={"Query": keyword, "Count": max(1, min(limit, 10))}, headers={
                    "Authorization": f"Bearer {secret}", "X-Request-Timestamp": str(int(time.time())),
                })
                data = r.json()
                if data.get("Code") != 90001 or attempt:  # 90001 服务端错误可重试一次
                    break
        code = data.get("Code")
        if code != 0:
            raise RuntimeError(f"知乎：{self._ERRORS.get(code, data.get('Message') or code)}")
        return [
            TrendItem(title=it["Title"], source=self.name, url=it.get("Url", ""),
                      heat=f"{it.get('VoteUpCount', 0)}赞", snippet=_TAG.sub("", it.get("ContentText") or "")[:200])
            for it in (data.get("Data") or {}).get("Items") or [] if it.get("Title")
        ]


def _prefer_keyword(items: list[TrendItem], keyword: str, limit: int) -> list[TrendItem]:
    """热榜类来源：关键词命中的排前面；命中不足时用整榜补齐，交给模型判断相关性。"""
    if not keyword:
        return items[:limit]
    words = [w for w in re.split(r"[\s,，、]+", keyword) if w]
    hit = [i for i in items if any(w in i.title or w in i.snippet for w in words)]
    rest = [i for i in items if i not in hit]
    return (hit + rest)[:limit]


class XiaohongshuSource:
    """小红书笔记搜索：必须扫码登录（游客会话没有搜索权限），实现见 xhs.py。"""

    name, label = "xiaohongshu", "小红书"

    async def fetch(self, keyword: str, limit: int) -> list[TrendItem]:
        cookie = credentials.get("xhs_cookie")
        if not cookie:
            raise NotConfigured("没登录小红书，在「数据来源」里扫码登录")
        if not keyword:
            return []
        from mediaflow.sources.xhs import search
        return await search(keyword, limit, cookie, timeout=get_settings().source_timeout)


class WechatSource:
    """微信公众号文章：搜狗微信搜索（weixin.sogou.com），无需配置。

    做法参考 zjp1997720/wechat-article-search。搜得太频繁搜狗会要求验证码，此时报错由上层标为失败。
    """

    name, label = "wechat", "微信文章"

    async def fetch(self, keyword: str, limit: int) -> list[TrendItem]:
        if not keyword:
            return []
        from bs4 import BeautifulSoup

        async with httpx.AsyncClient(timeout=get_settings().source_timeout) as c:
            r = await c.get("https://weixin.sogou.com/weixin", params={"type": "2", "query": keyword, "ie": "utf8"},
                            headers={"User-Agent": DESKTOP_UA, "Accept-Language": "zh-CN,zh;q=0.9"})
        if r.status_code in (301, 302) or "antispider" in str(r.url) or "antispider" in r.text[:3000]:
            raise RuntimeError("搜狗微信要求验证码（搜得太频繁），稍后再试")
        r.raise_for_status()
        out = []
        for li in BeautifulSoup(r.text, "html.parser").select("ul.news-list > li"):
            a = li.select_one("h3 a")
            if not a or not a.get_text(strip=True):
                continue
            href = a.get("href", "")
            account = li.select_one("span.all-time-y2")
            m = re.search(r"timeConvert\('(\d+)'\)", str(li))
            date = time.strftime("%Y-%m-%d", time.localtime(int(m.group(1)))) if m else ""
            out.append(TrendItem(
                title=a.get_text("", strip=True)[:80], source=self.name,
                url=("https://weixin.sogou.com" + href) if href.startswith("/") else href,
                heat=" · ".join(x for x in (account.get_text(strip=True) if account else "", date) if x),
                snippet=(li.select_one("p.txt-info").get_text("", strip=True) if li.select_one("p.txt-info") else "")[:200],
            ))
        return out[:limit]


_WBI_ENC = [46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
            33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13]


def _parse_cookie(raw: str) -> dict[str, str]:
    out = {}
    for part in raw.split(";"):
        k, sep, v = part.strip().partition("=")
        if sep and k:
            out[k] = v
    return out


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
        user_ck = credentials.get("bilibili_cookie")
        if user_ck:
            for k, v in _parse_cookie(user_ck).items():
                c.cookies.set(k, v, domain=".bilibili.com")
            if "buvid3" in c.cookies:
                return
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
            params = {"search_type": "video", "keyword": keyword, "order": "totalrank",
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
                    title=t, source=self.name, heat=f"{it.get('play', '')}播放",
                    url=f"https://www.bilibili.com/video/{it.get('bvid', '')}",
                    snippet=html.unescape(_TAG.sub("", it.get("description", "")))[:200], ref=it.get("bvid", ""),
                ))
        return out

    async def _ranking(self, c: httpx.AsyncClient, limit: int) -> list[TrendItem]:
        """没有关键词时用全站排行榜。"""
        r = await c.get("https://api.bilibili.com/x/web-interface/ranking/v2", params={"rid": 0, "type": "all"})
        r.raise_for_status()
        if r.json().get("code") not in (0, None):
            raise RuntimeError(f"B站排行榜被风控（code={r.json().get('code')}）")
        return [
            TrendItem(title=it["title"], source=self.name, heat=str((it.get("stat") or {}).get("view", "")), kind="hot",
                      url=f"https://www.bilibili.com/video/{it.get('bvid', '')}")
            for it in (r.json().get("data") or {}).get("list", [])[:limit] if it.get("title")
        ]


class DouyinSource:
    """抖音：配了登录 Cookie 就用网页版综合搜索接口，否则退回抖音热榜。

    搜索接口未登录会返回 status_code=2483「请先登录」。签名用 a_bogus（见 douyin_abogus/）；
    实测旧的 X-Bogus 反而会被判 antispam（hit_shark，返回空列表）。参数/请求头参考 MediaCrawler：
    webid、uifid、verifyFp/fp 都取自用户 Cookie，并带 uifid / x-tt-argus 头。
    """

    name, label = "douyin", "抖音"

    async def fetch(self, keyword: str, limit: int) -> list[TrendItem]:
        cookie = credentials.get("douyin_cookie")
        if cookie and keyword:
            return await self._search(keyword, limit, cookie)
        return await self._hot(keyword, limit)

    async def _search(self, keyword: str, limit: int, cookie: str) -> list[TrendItem]:
        from mediaflow.sources import douyin

        async with httpx.AsyncClient(timeout=get_settings().source_timeout) as c:
            for attempt in range(2):  # 实测偶尔会无理由返回空列表，重试一次通常就有
                data = await douyin.api(c, "/aweme/v1/web/general/search/single/", {
                    "search_channel": "aweme_general", "enable_history": "1", "keyword": keyword,
                    "search_source": "tab_search", "query_correct_type": "1", "is_filter_search": "0",
                    "from_group_id": "", "offset": "0", "count": str(max(1, min(limit, 20))),
                    "need_filter_settings": "1", "list_type": "multi",
                }, cookie, referer=f"https://www.douyin.com/search/{quote(keyword)}?type=general")
                if data.get("data") or attempt:
                    break
                await asyncio.sleep(1)
        out = []
        for raw in data.get("data") or data.get("aweme_list") or []:
            aw = (raw.get("aweme_info") or raw.get("item") or raw) if isinstance(raw, dict) else {}
            desc, aid = " ".join((aw.get("desc") or "").split()), aw.get("aweme_id")
            if not desc or not aid:
                continue
            st = aw.get("statistics") or {}
            out.append(TrendItem(
                title=desc[:80], source=self.name, snippet=desc[:200],
                heat=f"{st.get('digg_count', 0)}赞", url=f"https://www.douyin.com/video/{aid}", ref=str(aid),
            ))
        return out[:limit]

    async def _hot(self, keyword: str, limit: int) -> list[TrendItem]:
        async with httpx.AsyncClient(timeout=get_settings().source_timeout) as c:
            r = await c.get(
                "https://www.iesdouyin.com/web/api/v2/hotsearch/billboard/word/",
                headers={"User-Agent": MOBILE_UA, "Referer": "https://www.douyin.com/"},
            )
        r.raise_for_status()
        items = [
            TrendItem(title=it["word"], source=self.name, heat=str(it.get("hot_value", "")), kind="hot",
                      url=f"https://www.douyin.com/search/{quote(it['word'])}")
            for it in r.json().get("word_list", []) if it.get("word")
        ]
        return _prefer_keyword(items, keyword, limit)


ALL_SOURCES = [XiaohongshuSource(), ZhihuSource(), BaiduSource(), DouyinSource(), BilibiliSource(), WeiboSource(),
               WechatSource()]
