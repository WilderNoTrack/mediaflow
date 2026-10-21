"""每篇稿子照着哪些帖子来（参考帖）：文案可以学好几篇，配图只照其中一篇（一套图必须统一）。

draft.reference = {主参考帖的字段…, "local": [原图缓存], "extra": [其他文案参考帖…]}
- 主参考帖：配图一张对一张照着它的原图做，所以必须是图文笔记；文案也学它
- extra（最多 MAX_EXTRA 篇）：只给文案学标题公式、结构和信息密度，不参与出图

选的顺序：
1. 用户给了链接（可以好几篇）：第一篇图文笔记当主参考帖，其余当文案参考；
2. 选题自带的原爆款（复刻选题）/ 选题来源笔记 当主参考帖；
3. 对标账号的爆款里让模型挑：结构最像的当主参考帖，再挑一两篇当文案参考；
4. 都没有：按选题去小红书搜，最热的图文当主参考帖，接下来几篇当文案参考。
主参考帖的原图全部缓存到本地（小红书图片地址会过期），草稿上记下来，界面能对照着看。
"""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlmodel import Session, select

from mediaflow.agents import prompts
from mediaflow.domain.models import Benchmark, BenchmarkStatus, Topic
from mediaflow.llm.client import LLM, LLMError, complete_json
from mediaflow.research.types import count_num
from mediaflow.services.refs import cache_local

logger = logging.getLogger(__name__)

MAX_IMAGES = 9
MAX_EXTRA = 2
KEEP = ("title", "url", "creator", "likes", "content", "tags", "images", "cover")
EXTRA_KEEP = ("title", "url", "creator", "likes", "content", "tags", "why", "kind")
_LINK = re.compile(r"https?://[^\s，。！？、）】<>\"']+")


def split_links(text: str) -> list[str]:
    """从用户贴的文字里拆出一个或多个笔记链接（小红书分享文字里链接前后都有别的字）；没有链接就原样当一条。"""
    links = list(dict.fromkeys(_LINK.findall(text or "")))
    return links or ([text.strip()] if (text or "").strip() else [])


class RefError(ValueError):
    """用户给的链接用不了（不是小红书笔记、是视频、没登录、拿不到），信息直接给用户看。"""


async def _detail(url: str, *, need_images: bool = True) -> dict:
    from mediaflow.sources import xhs

    kind, native = await xhs.resolve_link(url)
    if kind != "post":
        raise RefError("这不是小红书笔记链接（要笔记页的链接，不是主页）")
    d = await xhs.post_detail(native, comments=0)
    if d.kind == "视频" and need_images:
        raise RefError("这篇是视频笔记，没有图可以照着做，换一篇图文笔记")
    return {"title": d.title, "url": d.url, "creator": d.author, "likes": d.likes, "content": d.content[:800],
            "tags": d.tags[:10], "images": [] if d.kind == "视频" else d.images[:MAX_IMAGES],
            "cover": d.cover or (d.images[:1] or [""])[0], "kind": d.kind}


async def _read(url: str, *, need_images: bool) -> dict:
    from mediaflow.research.types import Unsupported

    try:
        return await _detail(url, need_images=need_images)
    except RefError:
        raise
    except Unsupported as e:
        raise RefError(f"{e}（读别人的笔记要用小红书登录态）") from e
    except Exception as e:  # noqa: BLE001 - 网络/风控等，原因告诉用户
        raise RefError(f"这篇笔记没读到：{e}") from e


async def from_url(url: str) -> dict:
    """草稿页换配图参考：用户贴的一篇小红书图文笔记 → 主参考帖（含本地缓存的原图）。"""
    links = split_links(url)
    if not links:
        raise RefError("没看到链接")
    return await _finish({**await _read(links[0], need_images=True), "source": "user", "why": "你指定的参考帖"})


async def from_links(text: str) -> dict:
    """写稿时用户给的一篇或几篇链接：都读出来，第一篇图文当主参考帖（配图照它），其余只给文案参考。
    视频笔记也能当文案参考；一篇都读不出来、或读不到的那篇原因直接告诉用户。"""
    links = split_links(text)[: 1 + MAX_EXTRA + 2]
    posts = []
    for i, u in enumerate(links):
        try:
            posts.append(await _read(u, need_images=False))
        except RefError as e:
            raise RefError(f"第 {i + 1} 个链接：{e}" if len(links) > 1 else str(e)) from e
    main = next((p for p in posts if p.get("kind") != "视频" and (p.get("images") or p.get("cover"))), None)
    if main is None:
        raise RefError("给的都是视频笔记，配图没有可以照着做的，至少给一篇图文笔记")
    extra = [_slim({**p, "why": "你指定的参考帖"}) for p in posts if p is not main][:MAX_EXTRA + 2]
    return await _finish({**main, "source": "user", "why": "你指定的参考帖"}, extra)


def _slim(p: dict) -> dict:
    out = {k: p[k] for k in EXTRA_KEEP if p.get(k)}
    if out.get("content"):
        out["content"] = " ".join(str(out["content"]).split())[:600]
    return out


slim = _slim  # 只留文案参考要用的字段


async def _finish(ref: dict, extra: list[dict] | None = None) -> dict:
    imgs = [u for u in ref.get("images") or [] if u] or ([ref["cover"]] if ref.get("cover") else [])
    ref["local"] = await cache_local(imgs[:MAX_IMAGES]) if imgs else []
    ref.pop("kind", None)
    ref["extra"] = extra or []
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


async def _choose(llm: LLM, topic: Topic, cands: list[dict], *, main_needed: bool = True) -> tuple[dict | None, list[dict], str]:
    """从对标爆款里挑：(主参考帖, 文案参考帖们, 为什么)。main_needed=False 时主参考帖已经有了，只挑文案参考。"""
    want = MAX_EXTRA
    if len(cands) == 1:
        return (cands[0], [], "对标账号里的爆款") if main_needed else (None, [{**cands[0], "why": "对标账号里的爆款"}], "")
    try:
        data = await complete_json(llm, [
            {"role": "system", "content": prompts.REF_PICK_SYSTEM},
            {"role": "user", "content": prompts.REF_PICK_USER.format(
                untrusted_notice=prompts.UNTRUSTED_NOTICE, topic=topic.title, angle=topic.angle or "（无）",
                posts="\n".join(f"{i + 1}. {c.get('title', '')}｜{c.get('creator', '')}｜{c.get('likes') or '-'}赞"
                                f"｜{len(c.get('images') or []) or 1}张图" for i, c in enumerate(cands)))},
        ], temperature=0.2)
        n = int(data.get("no") or 0)
        also = [int(x) for x in (data.get("also") or []) if str(x).strip().isdigit()]
        if 1 <= n <= len(cands):
            why = str(data.get("why") or "")[:80] or "和这篇选题结构最像的爆款"
            picked = [n] + [x for x in also if 1 <= x <= len(cands) and x != n]
            main = cands[n - 1] if main_needed else None
            rest = picked[1:] if main_needed else picked
            extra = [{**cands[x - 1], "why": "同领域爆款，学标题和结构"} for x in rest][:want]
            if not main_needed and extra:
                extra[0]["why"] = why
            return main, extra, why
    except (LLMError, TypeError, ValueError) as e:
        logger.info("挑参考帖失败，按点赞取：%s", e)
    if main_needed:
        return cands[0], [{**c, "why": "对标账号里点赞高的爆款"} for c in cands[1:1 + want]], "对标账号里点赞最高的爆款"
    return None, [{**c, "why": "对标账号里点赞高的爆款"} for c in cands[:want]], ""


async def _search(topic: Topic) -> dict | None:
    from mediaflow.sources import xhs

    try:
        posts = [p for p in await xhs.search_hot_authors(topic.title[:30]) if p.get("kind") != "视频"]
    except Exception as e:  # noqa: BLE001 - 没登录/风控：就没有参考帖
        logger.info("按选题搜参考帖失败：%s", e)
        return None
    if not posts:
        return None
    top = sorted(posts[:10], key=lambda x: -count_num(x.get("likes")))
    as_ref = [{"title": p["title"], "url": p["url"], "creator": p.get("name", ""), "likes": p.get("likes", ""),
               "cover": p.get("cover", "")} for p in top]
    return {**as_ref[0], "why": "小红书上这个选题最热的图文笔记",
            "extra": [{**x, "why": "这个选题的热门笔记"} for x in as_ref[1:1 + MAX_EXTRA]]}


def _same(a: dict, b: dict | None) -> bool:
    return bool(b) and ((a.get("url") and a.get("url") == b.get("url")) or a.get("title") == b.get("title"))


async def pick(session: Session, llm: LLM, account_id: str, topic: Topic, *, url: str = "") -> tuple[dict, str]:
    """返回 (参考帖, 没有参考帖时的原因)。用户给的链接用不了会抛 RefError。"""
    if url.strip():
        return await from_links(url), ""
    ref: dict[str, Any] | None = None
    extra: list[dict] = []
    if (topic.reference or {}).get("title"):
        ref = {**{k: topic.reference[k] for k in (*KEEP, "creator") if topic.reference.get(k)},
               "source": "topic", "why": "这个选题就是照着它出的"}
    elif "xiaohongshu.com" in (topic.source_url or "") or "xhslink" in (topic.source_url or ""):
        try:
            ref = {**await _detail(topic.source_url), "source": "topic", "why": "这个选题是从这篇笔记来的"}
        except Exception as e:  # noqa: BLE001
            logger.info("选题来源笔记没读到：%s", e)
    cands = [c for c in _samples(session, account_id) if not _same(c, ref)]
    if cands:
        chosen, extra, why = await _choose(llm, topic, cands, main_needed=ref is None)
        if ref is None and chosen:
            ref = {**chosen, "source": "benchmark", "why": why}
    if ref is None:
        ref = await _search(topic)
        if ref:
            ref["source"] = "search"
            extra = ref.pop("extra", [])
    if ref is None:
        return {}, "还没有对标账号，也没连小红书，找不到可以照着做的帖子"
    return await _finish(await _fill_images(ref), [_slim(x) for x in extra if not _same(x, ref)][:MAX_EXTRA]), ""
