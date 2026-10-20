"""对标账号：找候选 → 选 1-3 个 → 各自读作品挑爆款、看详情、拆打法 → 合成一套打法并换成你的主题 → 同步到账号。

整条流程由代码编排（和写稿一样），模型只做三件事：给候选打分、拆解单个账号的打法、把几个打法合成并换主题。
所有结论的原始数据（作品列表、爆款详情）都存进 Benchmark.samples，界面上能对照原帖。
"""

from __future__ import annotations

import json
import logging
import re
import string
from collections.abc import Callable
from itertools import zip_longest
from typing import Any

from sqlmodel import Session, col, select

from mediaflow.agents import prompts
from mediaflow.agents.checks import is_duplicate
from mediaflow.domain.models import (
    Account, Benchmark, BenchmarkStatus, JobKind, Rule, RuleSource, Topic, TopicStatus, utcnow,
)
from mediaflow.llm.client import LLM, complete_json
from mediaflow.research import service as research
from mediaflow.research.types import Post, count_num

logger = logging.getLogger(__name__)

MAX_BENCH = 3    # 一个账号最多同时对标几个
N_POSTS = 60     # 每个对标最多读多少条作品
N_DETAILS = 5    # 看几篇爆款详情
N_HITS = 12      # 给模型看的爆款列表长度
N_PROBE = 10     # 找候选时细看几个博主的主页（会筛掉主要做视频的号，所以多看几个）
MAX_VIDEO_SHARE = 0.4  # 作品里视频超过这个比例就不当图文对标
PROFILE_KEYS = ("theme", "audience", "content_style", "image_style", "topic_type")
LETTERS = string.ascii_uppercase

Emit = Callable[[str, str, dict[str, Any] | None], None]


def _noop(stage: str, message: str, data: dict[str, Any] | None = None) -> None:
    pass


def _dedupe(posts: list[Post]) -> list[Post]:
    """同一篇作品只留一次（平台翻页偶尔会重复返回，按 ID、再按标题+日期认）。"""
    seen: set[str] = set()
    out = []
    for p in posts:
        keys = {p.native.split("|")[0] or p.url, f"{p.title}|{p.published}"}
        if keys & seen:
            continue
        seen |= keys
        out.append(p)
    return out


def _note(p: Post) -> dict:
    return {"title": p.title, "likes": p.likes, "url": p.url, "cover": p.cover, "kind": p.kind, "date": p.published}


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
    if days:
        out["last_post"] = str(days[-1])
    likes = [_score(p) for p in posts if _score(p)]
    if likes:
        med = median(likes)
        out["median_likes"] = int(med)
        out["hit_rate"] = round(sum(1 for v in likes if v >= med * 3) / len(likes), 2)  # 3 倍中位数算爆款
    kinds = [p.kind for p in posts if p.kind]
    if kinds:
        out["video_share"] = round(kinds.count("视频") / len(kinds), 2)
    return out


def _uid(url: str) -> str:
    m = re.search(r"/user/profile/([0-9a-zA-Z]{16,32})", url or "")
    return m.group(1) if m else ""


# ── 查询 ────────────────────────────────────────────────────────────────


def listing(s: Session, account_id: str) -> list[Benchmark]:
    """按加入顺序列出对标。同一个博主拆好了两份的（旧版本或并发留下的），只留最早那份，多的直接删掉。"""
    rows = list(s.exec(select(Benchmark).where(Benchmark.account_id == account_id)
                       .order_by(col(Benchmark.created_at))).all())
    seen: set[str] = set()
    out, dup = [], []
    for b in rows:
        key = _uid(b.creator_url) or (b.creator_name.strip() if b.status == BenchmarkStatus.ready else "")
        if key and b.status == BenchmarkStatus.ready and key in seen:
            dup.append(b)
            continue
        if key and b.status == BenchmarkStatus.ready:
            seen.add(key)
        out.append(b)
    if dup:
        for b in dup:
            s.delete(b)
        s.commit()
    return out


def ready(s: Session, account_id: str) -> list[Benchmark]:
    return [b for b in listing(s, account_id) if b.status == BenchmarkStatus.ready]


def latest(s: Session, account_id: str, *, ready_only: bool = False) -> Benchmark | None:
    rows = ready(s, account_id) if ready_only else listing(s, account_id)
    return rows[-1] if rows else None


# ── 加对标 / 删对标 ──────────────────────────────────────────────────────


def add(s: Session, acc: Account, targets: list[str], *, theme: str = "", platform: str = "xiaohongshu",
        names: dict[str, str] | None = None):
    """登记要对标的账号并派一个后台任务去拆。返回 (job, 新加的 Benchmark 列表)。重复的跳过，超出上限报错。"""
    from mediaflow.jobs.queue import JobConflict, active_write_job, enqueue

    targets = [t.strip() for t in targets if t and t.strip()]
    if not targets:
        raise ValueError("请给至少一个对标账号：主页链接、笔记链接或博主名字")
    if not (theme.strip() or acc.theme):
        raise ValueError("先说一下你想做什么主题，比如「职场新人理财」")
    running = active_write_job(s, acc.id, JobKind.clone_creator)
    if running:
        raise JobConflict(running)
    for b in listing(s, acc.id):  # 上次失败的不占名额，直接清掉
        if b.status == BenchmarkStatus.failed:
            s.delete(b)
    s.commit()
    have = listing(s, acc.id)
    seen = {x for b in have for x in (b.target.strip(), b.creator_name, _uid(b.creator_url), _uid(b.target)) if x}
    fresh = [t for t in dict.fromkeys(targets) if t not in seen and not (_uid(t) and _uid(t) in seen)]
    if not fresh:
        raise ValueError("这些账号已经在对标了")
    if len(have) + len(fresh) > MAX_BENCH:
        left = MAX_BENCH - len(have)
        raise ValueError(f"最多同时对标 {MAX_BENCH} 个，现在已有 {len(have)} 个"
                         + (f"，这次最多再加 {left} 个" if left > 0 else "，先删掉一个再加"))
    if theme.strip() and theme.strip() != acc.theme:
        acc.theme, acc.updated_at = theme.strip(), utcnow()
        s.add(acc)
    new = [Benchmark(user_id=acc.user_id, account_id=acc.id, platform=platform, target=t, theme=theme.strip(),
                     creator_name=(names or {}).get(t, "")[:60]) for t in fresh]
    s.add_all(new)
    s.commit()
    job = enqueue(s, JobKind.clone_creator, user_id=acc.user_id, account_id=acc.id,
                  payload={"benchmark_ids": [b.id for b in new], "theme": theme.strip()})
    return job, new


def remove(s: Session, acc: Account, b: Benchmark):
    """删掉一个对标：它的复刻选题收起；还剩别的就重新合成一次（返回任务），一个不剩就清掉对标规则和方案。"""
    from mediaflow.jobs.queue import JobConflict, active_write_job, enqueue

    running = active_write_job(s, acc.id, JobKind.clone_creator)
    if running:
        raise JobConflict(running)
    for t in s.exec(select(Topic).where(Topic.account_id == acc.id, Topic.source == "benchmark",
                                        Topic.status == TopicStatus.new)).all():
        if (t.reference or {}).get("benchmark_id") == b.id:
            t.status = TopicStatus.dismissed
            s.add(t)
    was_ready = b.status == BenchmarkStatus.ready
    s.delete(b)
    s.commit()
    if not was_ready:
        return None
    if ready(s, acc.id):
        return enqueue(s, JobKind.clone_creator, user_id=acc.user_id, account_id=acc.id,
                       payload={"benchmark_ids": [], "theme": ""})
    _clear(s, acc)
    return None


def _clear(s: Session, acc: Account) -> None:
    for r in s.exec(select(Rule).where(Rule.account_id == acc.id, Rule.source == RuleSource.benchmark,
                                       Rule.active == True)).all():  # noqa: E712
        r.active = False
        s.add(r)
    for t in s.exec(select(Topic).where(Topic.account_id == acc.id, Topic.source == "benchmark",
                                        Topic.status == TopicStatus.new)).all():
        t.status = TopicStatus.dismissed
        s.add(t)
    acc.bench_plan = {}
    s.add(acc)
    s.commit()


# ── 后台任务：逐个拆解 + 合成 ────────────────────────────────────────────


async def run(s: Session, llm: LLM, account_id: str, bench_ids: list[str], theme: str = "",
              *, emit: Emit = _noop) -> dict:
    acc = s.get(Account, account_id)
    if acc is None:
        raise LookupError("账号不存在")
    todo = [b for i in bench_ids if (b := s.get(Benchmark, i)) is not None and b.account_id == account_id]
    errors = []
    for n, b in enumerate(todo):
        prefix = f"（{n + 1}/{len(todo)}）" if len(todo) > 1 else ""
        try:
            await _analyze_one(s, llm, b, acc, emit, prefix)
        except _Duplicate as e:
            emit("warning", str(e), None)
            s.delete(b)
            s.commit()
        except Exception as e:  # noqa: BLE001 - 一个失败不拖累其他，最后没有可用的才报错
            logger.warning("拆解对标失败 %s：%s", b.target, e)
            b.status, b.error, b.updated_at = BenchmarkStatus.failed, str(e) or type(e).__name__, utcnow()
            s.add(b)
            s.commit()
            errors.append(f"{b.creator_name or b.target[:30]}：{b.error}")
            if len(todo) > 1:
                emit("warning", f"「{b.creator_name or b.target[:20]}」没拆成（{b.error}），先用其他的", None)
    if not ready(s, account_id):
        raise RuntimeError("；".join(errors) or "没有可用的对标账号")
    out = await _synthesize(s, llm, acc, theme or acc.theme, emit)
    from mediaflow.services import visual

    await visual.learn_quietly(s, account_id, emit)  # 能看图的话顺手学配图模板
    s.refresh(acc)
    out["visual_pages"] = [p["type"] for p in visual.pages(acc.visual)]
    return out


async def analyze(session: Session, llm: LLM, bench_id: str, *, emit: Emit = _noop) -> Benchmark:
    """只拆一个（兼容旧调用）：拆完和已有的对标一起合成。"""
    b = session.get(Benchmark, bench_id)
    if b is None:
        raise LookupError("对标记录不存在")
    await run(session, llm, b.account_id, [bench_id], b.theme, emit=emit)
    session.refresh(b)
    return b


class _Duplicate(Exception):
    pass


async def _analyze_one(s: Session, llm: LLM, b: Benchmark, acc: Account, emit: Emit, prefix: str) -> None:
    label = research.PLATFORM_LABELS.get(b.platform, b.platform)
    what = "链接里的博主" if "http" in b.target else f"「{b.target[:30]}」"
    emit("find", f"{prefix}在{label}上找{what}…", None)
    found = await research.resolve_creator(b.platform, b.target)
    creator, posts = await research.creator_posts_raw(b.platform, found.native, N_POSTS)
    posts = _dedupe(posts)
    if not posts:
        raise LookupError(f"「{creator.name or b.target}」没有公开作品，换一个对标账号吧")
    url = creator.url or found.url
    if _uid(url) and any(_uid(o.creator_url) == _uid(url) for o in listing(s, acc.id) if o.id != b.id):
        raise _Duplicate(f"「{creator.name}」已经在对标了，跳过")
    stats = _stats(posts)
    b.creator_name = creator.name or found.name
    b.creator_url = url
    b.creator_info = {"fans": creator.fans or found.fans, "desc": creator.desc or found.desc,
                      **{k: v for k, v in creator.extra.items() if v}, **stats}
    s.add(b)
    s.commit()
    emit("find", f"{prefix}找到「{b.creator_name}」（{b.creator_info.get('fans') or '粉丝数未知'}粉），读了 {len(posts)} 篇作品",
         {"creator": b.creator_name})

    if (stats.get("video_share") or 0) > MAX_VIDEO_SHARE:
        emit("warning", f"{prefix}「{b.creator_name}」主要做视频（{int(stats['video_share'] * 100)}%），只拆它的图文笔记", None)
    pics = [p for p in posts if p.kind != "视频"]
    hits = sorted(pics or posts, key=lambda p: -_score(p))[:N_HITS]
    details: list[dict] = []
    for i, p in enumerate(hits[:N_DETAILS]):
        emit("detail", f"{prefix}在看「{b.creator_name}」的爆款 {i + 1}/{min(N_DETAILS, len(hits))}：{p.title[:20]}", None)
        try:
            d = await research.post_detail_raw(b.platform, p.native)
        except Exception as e:  # noqa: BLE001 - 单篇失败不影响整体，如实记下
            logger.warning("对标详情失败 %s：%s", p.native, e)
            emit("warning", f"「{p.title[:20]}」详情没拿到（{e}），跳过", None)
            continue
        details.append({"title": d.title, "likes": d.likes, "collects": d.collects, "comments": d.comments,
                        "kind": d.kind or p.kind, "date": d.published or p.published, "url": d.url or p.url,
                        "content": d.content[:800],
                        "tags": d.tags[:10], "top_comments": d.top_comments[:5], "images": d.images[:9]})
    by_title = {d["title"]: d for d in details}
    b.samples = [{**_note(p), **by_title.get(p.title, {}), "cover": p.cover or next(iter(by_title.get(p.title, {}).get("images") or []), "")}
                 for p in hits]

    emit("analyze", f"{prefix}在拆解「{b.creator_name}」的打法：栏目、标题公式、开头、结构、视觉…", None)
    b.playbook = await complete_json(llm, [
        {"role": "system", "content": prompts.BENCH_ANALYZE_SYSTEM},
        {"role": "user", "content": prompts.BENCH_ANALYZE_USER.format(
            untrusted_notice=prompts.UNTRUSTED_NOTICE, creator=_creator_line(b), n_posts=len(posts),
            posts="\n".join(f"- {p.title}｜{p.kind}｜{p.likes or '-'}｜{p.published}" for p in posts),
            details=json.dumps([{k: v for k, v in d.items() if k != "images"} for d in details],
                               ensure_ascii=False, indent=1) if details else "（没拿到详情）",
        )},
    ], temperature=0.3)
    b.status, b.error, b.updated_at = BenchmarkStatus.ready, "", utcnow()
    s.add(b)
    s.commit()


def _creator_line(b: Benchmark) -> str:
    info = {k: b.creator_info.get(k) for k in ("posts_read", "per_week", "median_likes", "hit_rate", "video_share")
            if b.creator_info.get(k) is not None}
    return (f"{b.creator_name}｜粉丝 {b.creator_info.get('fans', '?')}｜简介：{b.creator_info.get('desc', '')}"
            f"｜{json.dumps(info, ensure_ascii=False)}")


async def _synthesize(s: Session, llm: LLM, acc: Account, theme: str, emit: Emit) -> dict:
    benches = ready(s, acc.id)[:MAX_BENCH]
    names = "、".join(f"「{b.creator_name}」" for b in benches)
    emit("adapt", (f"把 {names} 的打法合成一套，" if len(benches) > 1 else "") + f"按「{theme}」出复刻方案和选题…", None)
    plan = await complete_json(llm, [
        {"role": "system", "content": prompts.BENCH_ADAPT_SYSTEM},
        {"role": "user", "content": prompts.BENCH_ADAPT_USER.format(
            creators="\n".join(f"{LETTERS[i]}. {_creator_line(b)}" for i, b in enumerate(benches)),
            playbooks="\n\n".join(f"{LETTERS[i]}. {b.creator_name}\n{json.dumps(b.playbook, ensure_ascii=False)}"
                                  for i, b in enumerate(benches)),
            hits="\n".join(f"{LETTERS[i]}{j + 1}｜{x['title']}｜{x.get('likes') or '-'}"
                           for i, b in enumerate(benches) for j, x in enumerate(b.samples)),
            theme=theme,
            profile="\n".join(f"{k}: {getattr(acc, k)}" for k in PROFILE_KEYS if getattr(acc, k)) or "（空）",
        )},
    ], temperature=0.6)
    applied = _apply(s, benches, acc, plan, theme)
    plan["steps"] = [re.sub(r"[（(]?(?:套|对应|参考)?\s*[A-C]\d{1,2}[)）]?(?!\d)", "", _no_video(str(x))).strip()
                     for x in plan.get("steps") or [] if str(x).strip()]
    acc.bench_plan = {k: plan.get(k) for k in ("summary", "borrow", "pillars", "steps") if plan.get(k)} | {
        "theme": theme, "applied": applied, "fit": _fit(benches, plan.get("fit")), "creators": [b.creator_name for b in benches],
        "updated_at": utcnow().isoformat()}
    s.add(acc)
    s.commit()
    emit("done", f"复刻方案好了：{len(applied['topics'])} 个复刻选题，账号定位和 {len(applied['rules'])} 条写法规则已更新",
         {"benchmark_ids": [b.id for b in benches]})
    return {"creators": [b.creator_name for b in benches], "topics": len(applied["topics"]),
            "benchmark_ids": [b.id for b in benches]}


def _fit(benches: list[Benchmark], raw: Any) -> list[dict]:
    """每个对标和新主题是不是一个领域。只留跨领域的，前端拿来提醒「能学什么、学不了什么」。"""
    out = []
    for x in raw if isinstance(raw, list) else []:
        if not isinstance(x, dict) or x.get("same_domain") is not False:
            continue
        name = str(x.get("from") or "").strip()
        b = next((b for b in benches if b.creator_name and (b.creator_name in name or name in b.creator_name)), None)
        if b is None and len(benches) == 1:
            b = benches[0]
        if b is None:
            continue
        out.append({"benchmark_id": b.id, "creator": b.creator_name, "domain": str((b.playbook or {}).get("domain") or "")[:20],
                    "note": str(x.get("note") or "").strip()[:80]})
    return out


def _ref(benches: list[Benchmark], raw: Any) -> tuple[Benchmark | None, dict]:
    """「A3」「3」→ (对标账号, 对应爆款)。只有一个对标时允许不带字母。"""
    m = re.fullmatch(r"\s*([A-Za-z]?)\s*(\d+)\s*", str(raw or ""))
    if not m:
        return (benches[0] if len(benches) == 1 else None), {}
    bi = LETTERS.index(m.group(1).upper()) if m.group(1) else 0
    if bi >= len(benches):
        return None, {}
    b, j = benches[bi], int(m.group(2)) - 1
    return b, (b.samples[j] if 0 <= j < len(b.samples) else {})


def _norm(t: str) -> str:
    return re.sub(r"[\W_]+", "", t).lower()


_VIDEO = re.compile(r"视频|口播|vlog|直播|镜头前|拍摄", re.I)


def _no_video(text: str) -> str:
    """我们只做图文：方案里照搬来的视频说法（「想说的都在视频里了」「视频封面」）按分句去掉。"""
    parts = re.split(r"([，,；;。！!])", text)
    keep = "".join(a + b for a, b in zip(parts[0::2], parts[1::2] + [""]) if not _VIDEO.search(a))
    return keep.strip("，,；; ") or text


def _apply(s: Session, benches: list[Benchmark], acc: Account, plan: dict, theme: str) -> dict:
    """把方案写进账号：定位字段、写法规则、复刻选题。旧对标留下的规则和没用过的选题先清掉。"""
    prof = plan.get("profile") or {}
    changed: dict[str, Any] = {}
    for k in PROFILE_KEYS[1:]:
        v = _no_video(str(prof.get(k) or "").strip())
        if v:
            setattr(acc, k, v)
            changed[k] = v
    # 主题以用户说的为准；用户没说才用模型给的
    t = (theme or "").strip() or str(prof.get("theme") or "").strip()
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
    rules = [_no_video(str(x).strip())[:300] for x in plan.get("rules") or [] if str(x).strip()][:5]
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
        b, ref = _ref(benches, raw.get("ref"))
        if ref and _norm(title) == _norm(str(ref.get("title", ""))):
            continue  # 模型偷懒原样照抄了对方标题（还是对方领域的），不能算复刻选题
        reference = {k: ref[k] for k in ("title", "likes", "content", "tags", "url", "cover", "images") if ref.get(k)}
        if b is not None:
            reference |= {"creator": b.creator_name, "benchmark_id": b.id}
        t = Topic(user_id=acc.user_id, account_id=acc.id, title=title, angle=str(raw.get("angle", ""))[:200],
                  reason=str(raw.get("why", ""))[:200], source="benchmark",
                  source_url=str(ref.get("url", ""))[:500], reference=reference)
        s.add(t)
        topics.append(title)
        seen.append(title)
    s.commit()
    return {"profile": changed, "rules": rules, "topics": topics}


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


def plan_text(acc: Account, benches: list[Benchmark], limit: int = 1800) -> str:
    """合成方案 + 各对标打法摘要，注入写稿/选题上下文。"""
    if not benches:
        return ""
    plan = acc.bench_plan or {}
    lines = []
    if plan.get("summary"):
        lines.append(f"合成打法：{plan['summary']}")
    for x in plan.get("borrow") or []:
        if isinstance(x, dict) and x.get("how"):
            lines.append(f"- {x.get('aspect', '')}学「{x.get('from', '')}」：{x['how']}")
    each = max(300, (limit - sum(map(len, lines))) // len(benches))
    lines += [playbook_text(b, each) for b in benches]
    return "\n".join(lines)[:limit]


# ── 找同领域候选 ──────────────────────────────────────────────────────────


async def find_candidates(llm: LLM, theme: str, *, prefer: str = "", keywords: list[str] | None = None,
                          exclude: list[str] | None = None, platform: str = "xiaohongshu", limit: int = 6,
                          emit: Emit = _noop) -> dict:
    """按方向搜最热的笔记 → 汇总作者 → 细看几个人的主页数据 → 模型判断同领域贴合度、值得学什么。"""
    theme = theme.strip()
    if not theme:
        raise ValueError("先说一下想做什么方向，才能找同领域的对标账号")
    queries = [theme] + [k for k in keywords or [] if k and k not in theme][:2]
    skip = {x for x in exclude or [] if x}
    authors: dict[str, dict] = {}
    notes: list[str] = []
    for q in queries:
        emit("search", f"在小红书搜「{q}」的热门笔记…", None)
        try:
            rows = await research.hot_authors_raw(platform, q)
        except Exception as e:  # noqa: BLE001 - 一个词搜失败换下一个
            notes.append(f"搜「{q}」失败：{e}")
            continue
        for r in rows:
            if r["name"] in skip or r["user_id"] in skip:
                continue
            if r.get("kind") == "视频":
                continue  # 只要图文
            a = authors.setdefault(r["user_id"], {**r, "hits": []})
            if all(h["title"] != r["title"] for h in a["hits"]):
                a["hits"].append({"title": r["title"], "likes": r["likes"], "url": r["url"],
                                  "cover": r.get("cover", ""), "kind": r.get("kind", "")})
    # 再按领域词搜博主：名字/简介里就是做这个的号，通常比偶尔爆一篇的更值得学
    domain: list[dict] = []
    try:
        for c in await research.creators_raw(platform, theme, 15):
            uid = c.native.split("|")[0]
            if c.name in skip or uid in skip or uid in authors or count_num(c.fans) < 5000:
                continue
            domain.append({"user_id": uid, "name": c.name, "avatar": "", "native": c.native, "hits": []})
    except Exception as e:  # noqa: BLE001
        notes.append(f"按领域搜博主失败：{e}")
    if not authors and not domain:
        raise LookupError("；".join(notes) or f"没搜到「{theme}」相关的热门笔记，换个说法试试")
    by_hits = sorted(authors.values(), key=lambda a: (-len(a["hits"]), -sum(count_num(h["likes"]) for h in a["hits"])))
    pool = [x for pair in zip_longest(by_hits, domain) for x in pair if x]

    cands: list[dict] = []
    videos = 0
    probe = pool[:N_PROBE]
    for i, a in enumerate(probe):
        emit("probe", f"在看「{a['name']}」的主页和作品数据（{i + 1}/{len(probe)}）…", None)
        try:
            creator, posts = await research.creator_posts_raw(platform, a["native"], 30)
            posts = _dedupe(posts)
        except Exception as e:  # noqa: BLE001 - 风控时少看几个，如实告诉用户
            notes.append(f"「{a['name']}」主页没打开（{e}）")
            if "风控" in str(e) or "验证码" in str(e):
                break
            continue
        stats = _stats(posts)
        if (stats.get("video_share") or 0) > MAX_VIDEO_SHARE:
            videos += 1
            continue  # 主要做视频的号：我们做图文，学不来
        if (stats.get("median_likes") or 0) < 20 and count_num(creator.fans) < 1e4:
            continue  # 几乎没互动的小号不值得对标
        posts = [p for p in posts if p.kind != "视频"] or posts
        uid, _, tok = a["native"].partition("|")
        cands.append({
            "name": creator.name or a["name"], "avatar": a["avatar"] or creator.extra.get("avatar", ""),
            "fans": creator.fans,
            "desc": creator.desc[:80], "url": f"https://www.xiaohongshu.com/user/profile/{uid}"
                                             + (f"?xsec_token={tok}&xsec_source=pc_search" if tok else ""),
            **{k: stats[k] for k in ("median_likes", "hit_rate", "per_week", "last_post", "posts_read") if k in stats},
            "hits": a["hits"][:2],
            "top": [{"title": p.title, "likes": p.likes, "url": p.url}
                    for p in sorted(posts, key=lambda p: -_score(p))[:3]],
            # 主页按小红书的样子展示：最火的几篇带封面
            "notes": [_note(p) for p in sorted(posts, key=lambda p: -_score(p))[:6]],
            "recent": [p.title for p in posts[:8]],
        })
    if videos:
        notes.append(f"筛掉了 {videos} 个主要做视频的号，只留图文博主")
    if not cands:
        raise LookupError("；".join(notes) or "候选博主的主页都没打开，稍后再试")

    emit("pick", f"看了 {len(cands)} 个号的数据，在判断谁最值得学…", None)
    try:
        out = await complete_json(llm, [
            {"role": "system", "content": prompts.BENCH_PICK_SYSTEM},
            {"role": "user", "content": prompts.BENCH_PICK_USER.format(
                untrusted_notice=prompts.UNTRUSTED_NOTICE, theme=theme, prefer=prefer.strip() or "无",
                candidates="\n".join(
                    f"{i + 1}｜{c['name']}｜{c['fans'] or '?'}｜{c['desc']}｜中位赞 {c.get('median_likes', '?')}，"
                    f"爆款率 {c.get('hit_rate', '?')}，周更 {c.get('per_week', '?')}，最近 {c.get('last_post', '?')}"
                    f"｜{' / '.join(c['recent'][:6])}" for i, c in enumerate(cands)),
            )},
        ], temperature=0.2)
        picks = {int(p["no"]): p for p in out.get("picks") or [] if str(p.get("no", "")).isdigit()}
    except Exception as e:  # noqa: BLE001 - 打分失败就按数据排，不影响用户挑
        logger.warning("候选打分失败：%s", e)
        picks = {}
    for i, c in enumerate(cands):
        p = picks.get(i + 1) or {}
        c["fit"] = float(p.get("fit", 6) or 0)
        c.update({k: str(p[k])[:40] for k in ("level", "reason", "learn") if p.get(k)})
        c.pop("recent", None)
    good = [c for c in cands if c["fit"] >= 5]
    dropped = len(cands) - len(good)
    good.sort(key=lambda c: (-c["fit"], -(c.get("median_likes") or 0)))
    res: dict[str, Any] = {"theme": theme, "candidates": good[:limit]}
    if dropped:
        notes.append(f"另有 {dropped} 个博主主要不做这个方向，没放进来")
    if notes:
        res["notes"] = notes
    return res


def store_candidates(s: Session, acc: Account, res: dict, prefer: str = "") -> None:
    """把找到的候选存到账号上，对标页按小红书的样子展示（对话里和对标页找的都存这里）。"""
    acc.bench_candidates = {**res, "prefer": prefer, "at": utcnow().isoformat()}
    s.add(acc)
    s.commit()


def start_find(s: Session, acc: Account, query: str = "", prefer: str = ""):
    """排一个「找同领域对标候选」的后台任务，进度在对标页显示。"""
    from mediaflow.jobs.queue import enqueue

    query = (query or acc.theme).strip()
    if not query:
        raise ValueError("先说一下想做什么方向，才能找同领域的对标账号")
    return enqueue(s, JobKind.find_benchmarks, user_id=acc.user_id, account_id=acc.id,
                   payload={"query": query, "prefer": prefer.strip()})


async def run_find(s: Session, llm: LLM, account_id: str, query: str, prefer: str = "", emit: Emit = _noop) -> dict:
    acc = s.get(Account, account_id)
    if acc is None:
        raise LookupError("账号不存在")
    have = [x for b in listing(s, acc.id) for x in (b.creator_name, b.target) if x]
    res = await find_candidates(llm, query, prefer=prefer, keywords=acc.keywords, exclude=have, emit=emit)
    store_candidates(s, acc, res, prefer)
    n = len(res["candidates"])
    from mediaflow.agents.manager import post_note
    post_note(s, acc, f"按「{query}」在小红书找了 {n} 个同领域的号，放在「对标」页了，能看到各自的数据和最火的几篇。"
                      "挑 1-3 个点「学习选中的」；想换方向或有特别要求（比如粉丝少一点的、做图文的）直接跟我说。"
              if n else f"按「{query}」没找到合适的同领域账号，换个说法或者直接贴想对标的号给我。")
    emit("done", f"找到 {n} 个候选", {"count": n})
    return {"count": n}
