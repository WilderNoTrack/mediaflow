"""复刻对标账号：找到博主 → 读作品挑爆款 → 看爆款详情 → 拆打法 → 换主题出方案 → 同步到账号。

整条流程由代码编排（和写稿一样），模型只做两件事：拆解打法、换主题出方案。
所有结论的原始数据（作品列表、爆款详情）都存进 Benchmark.samples，界面上能对照原帖。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from sqlmodel import Session, select

from mediaflow.agents import prompts
from mediaflow.agents.checks import is_duplicate
from mediaflow.domain.models import (
    Account, Benchmark, BenchmarkStatus, Rule, RuleSource, Topic, TopicStatus, utcnow,
)
from mediaflow.llm.client import LLM, complete_json
from mediaflow.research import service as research
from mediaflow.research.types import Post, count_num

logger = logging.getLogger(__name__)

N_POSTS = 60     # 最多读多少条作品
N_DETAILS = 5    # 看几篇爆款详情
N_HITS = 12      # 给模型看的爆款列表长度
PROFILE_KEYS = ("theme", "audience", "content_style", "image_style", "topic_type")

Emit = Callable[[str, str, dict[str, Any] | None], None]


def _noop(stage: str, message: str, data: dict[str, Any] | None = None) -> None:
    pass


def _score(p: Post) -> float:
    return count_num(p.likes) or count_num(p.views)


def _stats(posts: list[Post]) -> dict:
    from datetime import date
    from statistics import median

    out: dict[str, Any] = {"posts_read": len(posts)}
    days = sorted(date.fromisoformat(p.published) for p in posts if p.published)
    if len(days) >= 2:
        span = max((days[-1] - days[0]).days, 1)
        out["per_week"] = round(len(days) * 7 / span, 1)
        out["date_range"] = f"{days[0]}～{days[-1]}"
    likes = [_score(p) for p in posts if _score(p)]
    if likes:
        med = median(likes)
        out["median_likes"] = int(med)
        out["hit_rate"] = round(sum(1 for v in likes if v >= med * 3) / len(likes), 2)  # 3 倍中位数算爆款
    kinds = [p.kind for p in posts if p.kind]
    if kinds:
        out["video_share"] = round(kinds.count("视频") / len(kinds), 2)
    return out


async def analyze(session: Session, llm: LLM, bench_id: str, *, emit: Emit = _noop) -> Benchmark:
    b = session.get(Benchmark, bench_id)
    if b is None:
        raise LookupError("对标记录不存在")
    acc = session.get(Account, b.account_id)
    if acc is None:
        raise LookupError("账号不存在")
    try:
        await _run(session, llm, b, acc, emit)
    except Exception as e:
        b.status, b.error, b.updated_at = BenchmarkStatus.failed, str(e) or type(e).__name__, utcnow()
        session.add(b)
        session.commit()
        raise
    return b


async def _run(s: Session, llm: LLM, b: Benchmark, acc: Account, emit: Emit) -> None:
    label = research.PLATFORM_LABELS.get(b.platform, b.platform)
    what = "链接里的博主" if "http" in b.target else f"「{b.target[:30]}」"
    emit("find", f"在{label}上找{what}…", None)
    found = await research.resolve_creator(b.platform, b.target)
    creator, posts = await research.creator_posts_raw(b.platform, found.native, N_POSTS)
    if not posts:
        raise LookupError(f"「{creator.name or b.target}」没有公开作品，换一个对标账号吧")
    stats = _stats(posts)
    b.creator_name = creator.name or found.name
    b.creator_url = creator.url or found.url
    b.creator_info = {"fans": creator.fans or found.fans, "desc": creator.desc or found.desc,
                      **{k: v for k, v in creator.extra.items() if v}, **stats}
    s.add(b)
    s.commit()
    emit("find", f"找到「{b.creator_name}」（{b.creator_info.get('fans') or '粉丝数未知'}粉），读了 {len(posts)} 篇作品",
         {"creator": b.creator_name})

    ranked = sorted(posts, key=lambda p: -_score(p))
    hits = ranked[:N_HITS]
    details: list[dict] = []
    for i, p in enumerate(hits[:N_DETAILS]):
        emit("detail", f"在看爆款 {i + 1}/{min(N_DETAILS, len(hits))}：{p.title[:24]}", None)
        try:
            d = await research.post_detail_raw(b.platform, p.native)
        except Exception as e:  # noqa: BLE001 - 单篇失败不影响整体，如实记下
            logger.warning("对标详情失败 %s：%s", p.native, e)
            emit("warning", f"「{p.title[:20]}」详情没拿到（{e}），跳过", None)
            continue
        details.append({"title": d.title, "likes": d.likes, "collects": d.collects, "comments": d.comments,
                        "kind": d.kind, "date": d.published, "url": d.url, "content": d.content[:800],
                        "tags": d.tags[:10], "top_comments": d.top_comments[:5]})
    by_title = {d["title"]: d for d in details}
    b.samples = [by_title.get(p.title) or {"title": p.title, "likes": p.likes, "kind": p.kind,
                                            "date": p.published, "url": p.url} for p in hits]

    emit("analyze", "在拆解打法：栏目、标题公式、开头、结构、视觉…", None)
    creator_line = (f"{b.creator_name}｜粉丝 {b.creator_info.get('fans', '?')}｜简介：{b.creator_info.get('desc', '')}"
                    f"｜{json.dumps(stats, ensure_ascii=False)}")
    b.playbook = await complete_json(llm, [
        {"role": "system", "content": prompts.BENCH_ANALYZE_SYSTEM},
        {"role": "user", "content": prompts.BENCH_ANALYZE_USER.format(
            untrusted_notice=prompts.UNTRUSTED_NOTICE, creator=creator_line, n_posts=len(posts),
            posts="\n".join(f"- {p.title}｜{p.kind}｜{p.likes or '-'}｜{p.published}" for p in posts),
            details=json.dumps(details, ensure_ascii=False, indent=1) or "（没拿到详情）",
        )},
    ], temperature=0.3)
    s.add(b)
    s.commit()

    theme = b.theme or acc.theme
    emit("adapt", f"按「{theme}」出复刻方案和选题…", None)
    plan = await complete_json(llm, [
        {"role": "system", "content": prompts.BENCH_ADAPT_SYSTEM},
        {"role": "user", "content": prompts.BENCH_ADAPT_USER.format(
            creator=creator_line, playbook=json.dumps(b.playbook, ensure_ascii=False, indent=1),
            hits="\n".join(f"{i + 1}｜{x['title']}｜{x.get('likes') or '-'}" for i, x in enumerate(b.samples)),
            theme=theme,
            profile="\n".join(f"{k}: {getattr(acc, k)}" for k in PROFILE_KEYS if getattr(acc, k)) or "（空）",
        )},
    ], temperature=0.6)
    applied = _apply(s, b, acc, plan, theme)
    b.plan = {k: plan.get(k) for k in ("pillars", "steps") if plan.get(k)} | {"applied": applied}
    b.status, b.error, b.updated_at = BenchmarkStatus.ready, "", utcnow()
    s.add(b)
    s.commit()
    emit("done", f"复刻方案好了：{len(applied['topics'])} 个复刻选题，账号定位和 {len(applied['rules'])} 条写法规则已更新",
         {"benchmark_id": b.id})


def _apply(s: Session, b: Benchmark, acc: Account, plan: dict, theme: str) -> dict:
    """把方案写进账号：定位字段、写法规则、复刻选题。旧对标留下的规则和没用过的选题先清掉。"""
    prof = plan.get("profile") or {}
    changed: dict[str, Any] = {}
    for k in PROFILE_KEYS[1:]:
        v = str(prof.get(k) or "").strip()
        if v:
            setattr(acc, k, v)
            changed[k] = v
    # 主题以用户说的为准；用户没说才用模型给的
    t = (b.theme or "").strip() or str(prof.get("theme") or "").strip() or theme
    if t:
        acc.theme = changed["theme"] = t
    kws = [str(x).strip() for x in prof.get("keywords") or [] if str(x).strip()][:6]
    if kws:
        acc.keywords = changed["keywords"] = kws
    acc.updated_at = utcnow()
    s.add(acc)

    for r in s.exec(select(Rule).where(Rule.account_id == acc.id, Rule.source == RuleSource.benchmark,
                                       Rule.active == True)).all():  # noqa: E712
        r.active = False
        s.add(r)
    rules = [str(x).strip()[:300] for x in plan.get("rules") or [] if str(x).strip()][:5]
    for text in rules:
        s.add(Rule(user_id=acc.user_id, account_id=acc.id, text=text, source=RuleSource.benchmark))

    for t in s.exec(select(Topic).where(Topic.account_id == acc.id, Topic.source == "benchmark",
                                        Topic.status == TopicStatus.new)).all():
        t.status = TopicStatus.dismissed
        s.add(t)
    seen = list(s.exec(select(Topic.title).where(Topic.account_id == acc.id,
                                                 Topic.status == TopicStatus.used)).all())
    topics = []
    for raw in plan.get("topics") or []:
        title = str(raw.get("title", "")).strip()[:80]
        if not title or is_duplicate(title, seen):
            continue
        try:
            ref = b.samples[int(raw.get("ref")) - 1]
        except (TypeError, ValueError, IndexError):
            ref = {}
        reference = {k: ref[k] for k in ("title", "likes", "content", "tags", "url") if ref.get(k)}
        reference |= {"creator": b.creator_name, "benchmark_id": b.id}
        t = Topic(user_id=acc.user_id, account_id=acc.id, title=title, angle=str(raw.get("angle", ""))[:200],
                  reason=str(raw.get("why", ""))[:200], source="benchmark",
                  source_url=str(ref.get("url", ""))[:500], reference=reference)
        s.add(t)
        topics.append(title)
        seen.append(title)
    s.commit()
    return {"profile": changed, "rules": rules, "topics": topics}


def latest(s: Session, account_id: str, *, ready_only: bool = False) -> Benchmark | None:
    from sqlmodel import col

    q = select(Benchmark).where(Benchmark.account_id == account_id)
    if ready_only:
        q = q.where(Benchmark.status == BenchmarkStatus.ready)
    return s.exec(q.order_by(col(Benchmark.created_at).desc())).first()


def playbook_text(b: Benchmark, limit: int = 1200) -> str:
    """注入写稿/选题上下文的打法摘要。"""
    p = b.playbook or {}
    lines = [f"对标账号：{b.creator_name}（{b.creator_info.get('fans', '')}粉）。{p.get('summary', '')}"]
    if p.get("persona"):
        lines.append(f"人设：{p['persona']}")
    if p.get("title_formulas"):
        lines.append("标题公式：" + "；".join(
            f"{f.get('formula', '')}（例：{f.get('example', '')}）" for f in p["title_formulas"][:5] if isinstance(f, dict)))
    if p.get("hooks"):
        lines.append("开头写法：" + "；".join(map(str, p["hooks"][:4])))
    if p.get("structure"):
        lines.append(f"正文结构：{p['structure']}")
    if p.get("tags"):
        lines.append(f"标签打法：{p['tags']}")
    if p.get("not_copyable"):
        lines.append("别照搬：" + "；".join(map(str, p["not_copyable"][:3])))
    return "\n".join(lines)[:limit]
