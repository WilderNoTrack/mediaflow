"""调研服务：把各平台能力统一成 4 个操作，给管家工具用。

- 短句柄：平台内部 ID（如小红书 user_id|xsec_token）换成 `xhs:c3`、`dy:p12` 这样的短 ref，
  模型只需原样传回，避免抄错长串（Anthropic《Writing effective tools for agents》的建议）。
- 限速：同一平台的调研请求串行且间隔 ≥ 1.5 秒，降低风控概率。
- 缓存：相同请求 10 分钟内直接复用。
- 输出：只保留对决策有用的字段，列表有上限并提示还有多少。
"""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import asdict
from typing import Any

from mediaflow.research.types import Creator, Post, PostDetail, Unsupported, count_num, fmt_count

PLATFORM_LABELS = {
    "xiaohongshu": "小红书", "douyin": "抖音", "bilibili": "B站", "weibo": "微博",
    "wechat": "微信公众号", "zhihu": "知乎", "baidu": "百度",
}
_PREFIX = {"xiaohongshu": "xhs", "douyin": "dy", "bilibili": "bili", "weibo": "wb", "wechat": "wx",
           "zhihu": "zh", "baidu": "bd"}
_BY_PREFIX = {v: k for k, v in _PREFIX.items()}

_MIN_GAP = 1.5
_CACHE_TTL = 600
_REF_MAX = 3000


def _impl(platform: str) -> Any:
    """返回平台的调研实现模块（实现了 search_creators / creator_posts / post_detail 中的若干个）。"""
    if platform == "xiaohongshu":
        from mediaflow.sources import xhs
        return xhs
    if platform == "douyin":
        from mediaflow.sources import douyin
        return douyin
    if platform == "bilibili":
        from mediaflow.sources import bilibili
        return bilibili
    if platform == "weibo":
        from mediaflow.sources import weibo
        return weibo
    if platform == "wechat":
        from mediaflow.sources import wechat
        return wechat
    return None


def capabilities() -> dict[str, list[str]]:
    """各平台支持的能力，写进工具说明里让模型知道。"""
    out: dict[str, list[str]] = {}
    for p in PLATFORM_LABELS:
        caps = ["搜内容"]
        m = _impl(p)
        for fn, label in (("search_creators", "搜博主"), ("creator_posts", "看博主作品"), ("post_detail", "看作品详情")):
            if m is not None and hasattr(m, fn):
                caps.append(label)
        out[p] = caps
    return out


class _Refs:
    def __init__(self) -> None:
        self._map: OrderedDict[str, tuple[str, str]] = OrderedDict()
        self._rev: dict[tuple[str, str, str], str] = {}
        self._n = 0

    def put(self, platform: str, kind: str, native: str) -> str:
        key = (platform, kind, native)
        if key in self._rev:
            return self._rev[key]
        self._n += 1
        ref = f"{_PREFIX[platform]}:{kind}{self._n}"
        self._map[ref] = (platform, native)
        self._rev[key] = ref
        while len(self._map) > _REF_MAX:
            old, (pp, nn) = self._map.popitem(last=False)
            self._rev.pop((pp, old.split(":")[1][0], nn), None)
        return ref

    def get(self, ref: str, kind: str) -> tuple[str, str]:
        ref = (ref or "").strip()
        hit = self._map.get(ref)
        if hit is None or ref.split(":")[-1][:1] != kind:
            what = "博主" if kind == "c" else "作品"
            raise LookupError(f"找不到{what} ref「{ref}」：可能是服务重启后失效了，请重新搜索后用新的 ref")
        return hit


refs = _Refs()
_locks: dict[str, asyncio.Lock] = {}
_last: dict[str, float] = {}
_cache: dict[tuple, tuple[float, Any]] = {}


async def _throttled(platform: str, key: tuple, fn: Callable[[], Awaitable[Any]]) -> Any:
    now = time.time()
    hit = _cache.get(key)
    if hit and now - hit[0] < _CACHE_TTL:
        return hit[1]
    lock = _locks.setdefault(platform, asyncio.Lock())
    async with lock:
        wait = _MIN_GAP - (time.time() - _last.get(platform, 0))
        if wait > 0:
            await asyncio.sleep(wait)
        try:
            result = await fn()
        finally:
            _last[platform] = time.time()
    _cache[key] = (time.time(), result)
    if len(_cache) > 500:
        for k in sorted(_cache, key=lambda k: _cache[k][0])[:100]:
            _cache.pop(k, None)
    return result


def _need(platform: str, fn: str, label: str):
    if platform not in PLATFORM_LABELS:
        raise Unsupported(f"不认识的平台「{platform}」，可选：{'、'.join(PLATFORM_LABELS)}")
    m = _impl(platform)
    if m is None or not hasattr(m, fn):
        caps = "、".join(capabilities()[platform])
        raise Unsupported(f"{PLATFORM_LABELS[platform]}暂不支持{label}（目前支持：{caps}）")
    return getattr(m, fn)


def _creator_out(c: Creator) -> dict:
    d = {"ref": refs.put(c.platform, "c", c.native), "name": c.name, "fans": c.fans, "posts": c.posts,
         "desc": c.desc, "url": c.url, **{k: v for k, v in c.extra.items() if v}}
    return {k: v for k, v in d.items() if v not in ("", None, [])}


def _post_out(p: Post) -> dict:
    d = {"ref": refs.put(p.platform, "p", p.native), "title": p.title, "date": p.published, "type": p.kind,
         "views": p.views, "likes": p.likes, "comments": p.comments, "collects": p.collects, "shares": p.shares, "url": p.url}
    return {k: v for k, v in d.items() if v not in ("", None)}


async def search_creators(platform: str, name: str, limit: int = 5) -> dict:
    fn = _need(platform, "search_creators", "搜博主")
    limit = max(1, min(limit, 10))
    found = await _throttled(platform, ("sc", platform, name, limit), lambda: fn(name, limit))
    if not found:
        return {"platform": platform, "creators": [], "hint": "没搜到，换个写法（去掉表情/后缀）再试"}
    return {"platform": platform, "creators": [_creator_out(c) for c in found]}


async def creator_posts(creator_ref: str, limit: int = 10, sort: str = "latest") -> dict:
    platform, native = refs.get(creator_ref, "c")
    fn = _need(platform, "creator_posts", "看博主作品")
    creator, posts = await _throttled(platform, ("cp", platform, native), lambda: fn(native, 30))
    total = len(posts)
    if sort == "top":
        posts = sorted(posts, key=lambda p: -(count_num(p.likes) or count_num(p.views)))
    limit = max(1, min(limit, 20))
    out = {"platform": platform, "creator": _creator_out(creator), "posts": [_post_out(p) for p in posts[:limit]]}
    stats = _stats(posts)
    if stats:
        out["stats"] = stats
    if total > limit:
        out["hint"] = f"共取到最近 {total} 条，只列了 {limit} 条；可调大 limit 或用 sort=top 看互动最高的"
    return out


def _stats(posts: list[Post]) -> str:
    """最近作品的更新频率和互动中位数，省得模型自己数。"""
    from datetime import date
    from statistics import median

    days = sorted(date.fromisoformat(p.published) for p in posts if p.published)
    parts = []
    if len(days) >= 2:
        span = max((days[-1] - days[0]).days, 1)
        parts.append(f"这 {len(days)} 条发布于 {days[0]}～{days[-1]}，约每周 {len(days) * 7 / span:.1f} 条")
    for label, vals in (("点赞", [count_num(p.likes) for p in posts if p.likes]),
                        ("播放", [count_num(p.views) for p in posts if p.views])):
        if vals:
            parts.append(f"{label}中位数 {fmt_count(int(median(vals)))}")
    return "；".join(parts)


async def post_detail(post_ref: str) -> dict:
    platform, native = refs.get(post_ref, "p")
    fn = _need(platform, "post_detail", "看作品详情")
    d: PostDetail = await _throttled(platform, ("pd", platform, native), lambda: fn(native))
    out = _post_out(d)
    out.update({"platform": platform, "author": d.author, "content": d.content, "tags": d.tags,
                "top_comments": d.top_comments})
    return {k: v for k, v in out.items() if v not in ("", None, [])}


def item_ref(platform: str, native: str) -> str:
    """关键词搜索结果（TrendItem.ref）也换成短句柄，方便接着看详情。"""
    return refs.put(platform, "p", native) if native and _impl(platform) is not None else ""


def as_dict(obj: Any) -> dict:
    return asdict(obj)


# ── 复刻对标账号用：直接拿数据类，不做截断 ────────────────────────────────


async def creator_posts_raw(platform: str, native: str, n: int = 60) -> tuple[Creator, list[Post]]:
    fn = _need(platform, "creator_posts", "看博主作品")
    return await _throttled(platform, ("cpr", platform, native, n), lambda: fn(native, n))


async def post_detail_raw(platform: str, native: str) -> PostDetail:
    fn = _need(platform, "post_detail", "看作品详情")
    return await _throttled(platform, ("pd", platform, native), lambda: fn(native))


def _norm(s: str) -> str:
    return "".join(ch for ch in (s or "").lower() if ch.isalnum())


async def resolve_creator(platform: str, target: str) -> Creator:
    """把用户给的「链接 / 名字 / 小红书号」解析成博主。

    名字搜索时优先完全同名，其次粉丝最多的（重名小号通常没几个粉丝）。
    """
    target = (target or "").strip()
    if not target:
        raise ValueError("请给一个对标账号：主页链接、笔记链接或博主名字")
    if platform == "xiaohongshu":
        from mediaflow.sources import xhs

        kind, native = await xhs.resolve_link(target)
        if kind == "post":
            d = await post_detail_raw(platform, native)
            if not d.author_native:
                raise LookupError("这篇笔记没拿到作者信息，换成博主主页链接试试")
            kind, native = "creator", d.author_native
        if kind == "creator":
            return Creator(platform=platform, name="", native=native)
    elif target.startswith("http"):
        raise Unsupported(f"{PLATFORM_LABELS.get(platform, platform)}暂不支持用链接找博主，请直接写博主名字")
    fn = _need(platform, "search_creators", "搜博主")
    found: list[Creator] = await _throttled(platform, ("sc", platform, target, 10), lambda: fn(target, 10))
    if not found:
        raise LookupError(f"没搜到「{target}」，换个写法（去掉表情/后缀）或直接贴主页链接")
    want = _norm(target)
    exact = [c for c in found if _norm(c.name) == want or want in _norm(c.desc)]
    pool = exact or found
    return max(pool, key=lambda c: count_num(c.fans))
