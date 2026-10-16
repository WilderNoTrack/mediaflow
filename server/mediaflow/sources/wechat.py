"""微信公众号调研：基于搜狗微信搜索（weixin.sogou.com），无需配置。

搜狗已不再提供公众号（type=1）搜索，所以：
- 搜公众号 = 按名字搜文章，再把文章的来源公众号聚合起来（名字完全一致的排前面）；
- 看公众号文章 = 用公众号名搜文章，只保留该号发的（只能拿到搜狗收录的部分，没有阅读/点赞数）；
- 看文章详情 = 解析搜狗跳转页拿到 mp.weixin.qq.com 临时链接，抓正文。
搜得太频繁搜狗会要求验证码，此时报错。
"""

from __future__ import annotations

import re
from collections import Counter
from contextlib import asynccontextmanager

import httpx

from mediaflow.research.types import Creator, Post, PostDetail, ms_date
from mediaflow.sources.base import DESKTOP_UA

S = "https://weixin.sogou.com"
_H = {"User-Agent": DESKTOP_UA, "Accept-Language": "zh-CN,zh;q=0.9"}
_JAR = httpx.Cookies()  # 搜狗的跳转链接要和搜索用同一组 Cookie（SNUID 等），否则会被当成爬虫


@asynccontextmanager
async def _client(timeout: float):
    async with httpx.AsyncClient(timeout=timeout, cookies=_JAR) as c:
        yield c
        _JAR.update(c.cookies)


def _check(r: httpx.Response) -> None:
    if r.status_code in (301, 302) or "antispider" in str(r.url) or "antispider" in r.text[:3000]:
        raise RuntimeError("搜狗微信要求验证码（搜得太频繁），稍后再试")
    r.raise_for_status()


async def articles(c: httpx.AsyncClient, query: str, page: int = 1) -> list[dict]:
    """搜狗微信文章搜索的一页结果：title / href / account / date / snippet。"""
    from bs4 import BeautifulSoup

    r = await c.get(f"{S}/weixin", params={"type": "2", "query": query, "ie": "utf8", "page": page}, headers=_H)
    _check(r)
    out = []
    for li in BeautifulSoup(r.text, "html.parser").select("ul.news-list > li"):
        a = li.select_one("h3 a")
        if not a or not a.get_text(strip=True):
            continue
        acc = li.select_one("span.all-time-y2")
        m = re.search(r"timeConvert\('(\d+)'\)", str(li))
        info = li.select_one("p.txt-info")
        href = a.get("href", "")
        out.append({"title": a.get_text("", strip=True), "href": href,
                    "url": (S + href) if href.startswith("/") else href,
                    "account": acc.get_text(strip=True) if acc else "",
                    "date": ms_date(m.group(1)) if m else "",
                    "snippet": info.get_text("", strip=True) if info else ""})
    return out


async def search_creators(name: str, limit: int = 5, timeout: float = 15):
    async with _client(timeout) as c:
        arts = await articles(c, name)
    cnt = Counter(a["account"] for a in arts if a["account"])
    names = sorted(cnt, key=lambda n: (n != name, name not in n, -cnt[n]))
    return [Creator(platform="wechat", name=n, native=n,
                    desc=next((a["title"] for a in arts if a["account"] == n), "")[:80],
                    extra={"说明": "搜狗只给出文章来源，不含粉丝数"}) for n in names[:limit]]


async def creator_posts(native: str, limit: int = 10, timeout: float = 15):
    import asyncio

    seen: dict[str, dict] = {}
    async with _client(timeout) as c:
        for page in (1, 2):
            for a in await articles(c, native, page):
                if a["account"] == native:
                    seen.setdefault(a["title"], a)
            if len(seen) >= limit:
                break
            await asyncio.sleep(1.0)
    posts = [Post(platform="wechat", title=a["title"][:80], native=a["href"], author=native,  # 搜狗跳转链接太长，详情里给正式链接
                  published=a["date"], kind="文章") for a in seen.values()]
    posts.sort(key=lambda p: p.published, reverse=True)
    creator = Creator(platform="wechat", name=native, native=native, posts=f"搜狗收录 {len(posts)} 篇",
                      extra={"说明": "只含搜狗收录的部分文章，没有阅读/点赞数"})
    return creator, posts[:limit]


async def post_detail(native: str, comments: int = 8, timeout: float = 15):
    from bs4 import BeautifulSoup

    async with _client(timeout) as c:
        url = native
        if native.startswith("/link"):
            r = await c.get(S + native, headers={**_H, "Referer": f"{S}/weixin"})
            _check(r)
            url = "".join(re.findall(r"url \+= '([^']*)'", r.text)).replace("@", "")
            if not url:
                raise RuntimeError("公众号文章链接已失效，请重新搜索")
        r = await c.get(url, headers=_H)
        r.raise_for_status()
    t = BeautifulSoup(r.text, "html.parser")
    body = t.select_one("#js_content")
    if body is None:
        raise RuntimeError("公众号文章打不开（可能已删除或需要在微信里看）")

    def txt(sel: str) -> str:
        el = t.select_one(sel)
        return el.get_text(" ", strip=True) if el else ""

    m = re.search(r"var ct = \"(\d+)\"", r.text) or re.search(r"create_time\s*[:=]\s*['\"]?(\d{9,})", r.text)
    return PostDetail(platform="wechat", title=txt("#activity-name"), native=native, url=url,
                      author=txt("#js_name"), kind="文章", content=body.get_text("\n", strip=True)[:1500],
                      published=ms_date(m.group(1)) if m else "")
