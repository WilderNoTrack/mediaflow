"""每篇稿子照着哪篇帖子来（参考帖）：写稿学它的结构，出图一张对一张照着它的原图做。

选参考帖的顺序：
1. 用户给了链接（对话里「照着这篇写」、草稿页「换一篇参考」）；
2. 选题自带的原爆款（复刻选题）；
3. 选题是从某篇小红书笔记来的（source_url）；
4. 对标账号的爆款里挑结构最合适的一篇（让模型挑，挑不了就按点赞）；
5. 都没有：按选题去小红书搜最热的图文笔记。
拿到后把原图全部缓存到本地（小红书图片地址会过期），草稿上记下来，界面能对照着看。
"""

from __future__ import annotations

import logging
from typing import Any

from sqlmodel import Session, select

from mediaflow.agents import prompts
from mediaflow.domain.models import Benchmark, BenchmarkStatus, Topic
from mediaflow.llm.client import LLM, LLMError, complete_json
from mediaflow.research.types import count_num
from mediaflow.services.refs import cache_local

logger = logging.getLogger(__name__)

MAX_IMAGES = 9
KEEP = ("title", "url", "creator", "likes", "content", "tags", "images", "cover")


class RefError(ValueError):
    """用户给的链接用不了（不是小红书笔记、是视频、没登录、拿不到），信息直接给用户看。"""


async def _detail(url: str) -> dict:
    from mediaflow.sources import xhs

    kind, native = await xhs.resolve_link(url)
    if kind != "post":
        raise RefError("这不是小红书笔记链接（要笔记页的链接，不是主页）")
    d = await xhs.post_detail(native, comments=0)
    if d.kind == "视频":
        raise RefError("这篇是视频笔记，没有图可以照着做，换一篇图文笔记")
    return {"title": d.title, "url": d.url, "creator": d.author, "likes": d.likes, "content": d.content[:800],
            "tags": d.tags[:10], "images": d.images[:MAX_IMAGES], "cover": d.cover or (d.images[:1] or [""])[0]}


async def from_url(url: str) -> dict:
    """用户贴的小红书笔记链接 → 参考帖（含本地缓存的原图）。"""
    from mediaflow.research.types import Unsupported

    try:
        ref = await _detail(url)
    except RefError:
        raise
    except Unsupported as e:
        raise RefError(f"{e}（读别人的笔记要用小红书登录态）") from e
    except Exception as e:  # noqa: BLE001 - 网络/风控等，原因告诉用户
        raise RefError(f"这篇笔记没读到：{e}") from e
    return await _finish({**ref, "source": "user", "why": "你指定的参考帖"})


async def _finish(ref: dict) -> dict:
    imgs = [u for u in ref.get("images") or [] if u] or ([ref["cover"]] if ref.get("cover") else [])
    ref["local"] = await cache_local(imgs[:MAX_IMAGES]) if imgs else []
    return {k: v for k, v in ref.items() if v not in (None, "", [])}


async def _fill_images(ref: dict) -> dict:
    """对标样本里只有前几篇有全部原图，其他只有封面：有链接就去补全。"""
    if len(ref.get("images") or []) > 1 or not ref.get("url"):
        return ref
    try:
        d = await _detail(ref["url"])
        return {**ref, **{k: v for k, v in d.items() if v}}
    except Exception as e:  # noqa: BLE001 - 补不全就只用封面
        logger.info("参考帖原图没补全 %s：%s", ref.get("url", "")[:60], e)
        return ref


def _samples(session: Session, account_id: str) -> list[dict]:
    benches = session.exec(select(Benchmark).where(
        Benchmark.account_id == account_id, Benchmark.status == BenchmarkStatus.ready)).all()
    out = []
    for b in benches:
        for x in b.samples or []:
            if x.get("kind") != "视频" and (x.get("images") or x.get("cover")):
                out.append({**{k: x[k] for k in KEEP if x.get(k)}, "creator": b.creator_name})
    out.sort(key=lambda x: -count_num(x.get("likes")))
    return out[:24]


async def _choose(llm: LLM, topic: Topic, cands: list[dict]) -> tuple[dict, str]:
    if len(cands) == 1:
        return cands[0], "对标账号里的爆款"
    try:
        data = await complete_json(llm, [
            {"role": "system", "content": prompts.REF_PICK_SYSTEM},
            {"role": "user", "content": prompts.REF_PICK_USER.format(
                untrusted_notice=prompts.UNTRUSTED_NOTICE, topic=topic.title, angle=topic.angle or "（无）",
                posts="\n".join(f"{i + 1}. {c.get('title', '')}｜{c.get('creator', '')}｜{c.get('likes') or '-'}赞"
                                f"｜{len(c.get('images') or []) or 1}张图" for i, c in enumerate(cands)))},
        ], temperature=0.2)
        n = int(data.get("no") or 0)
        if 1 <= n <= len(cands):
            return cands[n - 1], str(data.get("why") or "")[:80] or "和这篇选题结构最像的爆款"
    except (LLMError, TypeError, ValueError) as e:
        logger.info("挑参考帖失败，按点赞取第一篇：%s", e)
    return cands[0], "对标账号里点赞最高的爆款"


async def _search(topic: Topic) -> dict | None:
    from mediaflow.sources import xhs

    try:
        posts = [p for p in await xhs.search_hot_authors(topic.title[:30]) if p.get("kind") != "视频"]
    except Exception as e:  # noqa: BLE001 - 没登录/风控：就没有参考帖
        logger.info("按选题搜参考帖失败：%s", e)
        return None
    if not posts:
        return None
    p = max(posts[:10], key=lambda x: count_num(x.get("likes")))
    return {"title": p["title"], "url": p["url"], "creator": p.get("name", ""), "likes": p.get("likes", ""),
            "cover": p.get("cover", ""), "why": "小红书上这个选题最热的图文笔记"}


async def pick(session: Session, llm: LLM, account_id: str, topic: Topic, *, url: str = "") -> tuple[dict, str]:
    """返回 (参考帖, 没有参考帖时的原因)。用户给的链接用不了会抛 RefError。"""
    if url.strip():
        return await from_url(url.strip()), ""
    ref: dict[str, Any] | None = None
    if (topic.reference or {}).get("title"):
        ref = {**{k: topic.reference[k] for k in (*KEEP, "creator") if topic.reference.get(k)},
               "source": "topic", "why": "这个选题就是照着它出的"}
    elif "xiaohongshu.com" in (topic.source_url or "") or "xhslink" in (topic.source_url or ""):
        try:
            ref = {**await _detail(topic.source_url), "source": "topic", "why": "这个选题是从这篇笔记来的"}
        except Exception as e:  # noqa: BLE001
            logger.info("选题来源笔记没读到：%s", e)
    if ref is None and (cands := _samples(session, account_id)):
        chosen, why = await _choose(llm, topic, cands)
        ref = {**chosen, "source": "benchmark", "why": why}
    if ref is None:
        ref = await _search(topic)
        if ref:
            ref["source"] = "search"
    if ref is None:
        return {}, "还没有对标账号，也没连小红书，找不到可以照着做的帖子"
    return await _finish(await _fill_images(ref)), ""
