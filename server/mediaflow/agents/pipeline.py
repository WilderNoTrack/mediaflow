"""写稿流水线：选题 → 写稿 → 硬检查 + AI 质检 → 不合格就在最好的一版上按意见修改 → 存草稿。

和 v1 最大的区别：这是一条**由代码编排的固定流程**，不是让 LLM 自己决定下一步调什么工具。
写一篇稿子的步骤本来就是确定的，交给 ReAct 只会带来跳步、漏参数、乱填账号 ID。
模型只负责它擅长的部分：出选题、写、评。

手动「立即创作」、管家对话里「写一篇」、自动模式定时写，三个入口都只调 `write_draft`。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlmodel import Session, col, select

from mediaflow.agents import prompts
from mediaflow.agents.checks import body_len, body_range, clean_tags, hard_check
from mediaflow.agents.context import AccountContext, load_context
from mediaflow.config import get_settings
from mediaflow.domain.models import (
    Draft, DraftImage, ImageStatus, Topic, TopicStatus, Trigger, utcnow,
)
from mediaflow.llm.client import LLM, LLMError, complete_json
from mediaflow.services.topics import Fetcher, propose_topics

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 4  # 写 1 版 + 最多按质检意见改 3 轮
PASS_SCORE = 7.0

Emit = Callable[[str, str, dict[str, Any] | None], None]


def _noop(stage: str, message: str, data: dict[str, Any] | None = None) -> None:
    pass


@dataclass
class Candidate:
    title: str
    body: str
    tags: list[str]
    image_prompts: list[str]
    issues: list[str] = field(default_factory=list)
    evaluation: dict[str, Any] = field(default_factory=dict)
    score: float | None = None

    @property
    def passed(self) -> bool:
        return not self.issues and self.score is not None and self.score >= PASS_SCORE

    def rank(self) -> tuple[int, float]:
        # 没有硬伤的优先，其次看分数
        return (0 if self.issues else 1, self.score or 0.0)


async def _pick_topic(
    session: Session, llm: LLM, ctx: AccountContext, topic_id: str | None,
    hint: str, emit: Emit, fetch: Fetcher | None,
) -> Topic:
    if topic_id:
        t = session.get(Topic, topic_id)
        if t is None or t.account_id != ctx.account_id:
            raise LookupError("选题不存在或不属于这个账号")
        emit("topic", f"使用选题库里的选题：{t.title}", {"topic_id": t.id})
        return t
    if not hint:
        # 复刻模式：先按顺序用对标方案里的复刻选题
        bt = session.exec(select(Topic).where(
            Topic.account_id == ctx.account_id, Topic.source == "benchmark", Topic.status == TopicStatus.new,
        ).order_by(col(Topic.created_at))).first()
        if bt is not None:
            emit("topic", f"使用复刻选题：{bt.title}", {"topic_id": bt.id})
            return bt
    emit("topic", "正在搜热点、找选题…", None)
    proposal = await propose_topics(session, llm, ctx, direction=hint, count=3, fetch=fetch)
    if proposal.source_note:
        emit("warning", proposal.source_note, None)
    if not proposal.topics:
        if not hint:
            raise LLMError("没能想出和历史内容不重复的选题，换个方向试试")
        # 用户给了具体想法：热点里没挑出新选题时，直接把想法当选题写，而不是报错
        t = Topic(user_id=ctx.user_id, account_id=ctx.account_id, title=hint.strip()[:80], source="user")
        session.add(t)
        session.commit()
        session.refresh(t)
        emit("topic", f"按你的想法写：{t.title}", {"topic_id": t.id})
        return t
    t = proposal.topics[0]
    emit("topic", f"选定选题：{t.title}", {"topic_id": t.id, "angle": t.angle})
    return t


def _reference_block(topic: Topic) -> str:
    ref = topic.reference or {}
    if not ref.get("title"):
        return ""
    body = " ".join(str(ref.get("content", "")).split())[:600]
    return ("\n\n" + prompts.UNTRUSTED_NOTICE + "\n<external_data>\n"
            f"【参考爆款（{ref.get('creator', '对标账号')}，{ref.get('likes', '?')}赞）】\n标题：{ref['title']}\n"
            + (f"正文：{body}\n" if body else "")
            + (f"标签：{'、'.join(ref.get('tags') or [])}\n" if ref.get("tags") else "")
            + "</external_data>\n学它的标题公式、开头钩子、结构节奏和信息密度，内容必须换成本账号主题，不照抄任何句子。")


async def _generate(llm: LLM, ctx: AccountContext, topic: Topic, hint: str, feedback: str) -> Candidate:
    data = await complete_json(llm, [
        {"role": "system", "content": prompts.WRITER_SYSTEM},
        {"role": "user", "content": prompts.WRITER_USER.format(
            profile=ctx.profile_text(),
            rules=ctx.rules_text(),
            topic_title=topic.title,
            topic_angle=topic.angle or "自行决定",
            hint_block=f"用户补充要求：{hint}\n" if hint else "",
            feedback_block=f"\n【上一版的问题，这次必须改掉】\n{feedback}\n" if feedback else "",
        ) + _reference_block(topic)},
    ], temperature=0.85)
    return Candidate(
        title=str(data.get("title", "")).strip(),
        body=str(data.get("body", "")).strip(),
        tags=clean_tags(data.get("tags") or []),
        image_prompts=[str(p).strip() for p in (data.get("image_prompts") or []) if str(p).strip()][:9],
    )


def _length_req(ctx: AccountContext) -> str:
    lo, hi = body_range(ctx.rules)
    return f"，规则要求 {lo}–{hi} 字" if lo and hi else f"，规则要求不超过 {hi} 字" if hi else f"，规则要求至少 {lo} 字" if lo else ""


async def _revise(llm: LLM, ctx: AccountContext, c: Candidate, feedback: str) -> Candidate:
    """在已有的一版上按意见改，而不是推倒重写：重写每次都会冒出新问题，改稿才会越改越好。"""
    data = await complete_json(llm, [
        {"role": "system", "content": prompts.REVISER_SYSTEM},
        {"role": "user", "content": prompts.REVISER_USER.format(
            profile=ctx.profile_text(), rules=ctx.rules_text(), title=c.title, body=c.body,
            body_len=body_len(c.body), length_req=_length_req(ctx), tags="、".join(c.tags),
            images="\n".join(f"{i + 1}. {p}" for i, p in enumerate(c.image_prompts)) or "（无）",
            feedback=feedback or "- 整体再打磨一遍：开头更抓人、信息更具体",
        )},
    ], temperature=0.5)
    return Candidate(
        title=str(data.get("title", "")).strip() or c.title,
        body=str(data.get("body", "")).strip() or c.body,
        tags=clean_tags(data.get("tags") or []) or c.tags,
        image_prompts=[str(p).strip() for p in (data.get("image_prompts") or []) if str(p).strip()][:9] or c.image_prompts,
    )


async def _check(llm: LLM, ctx: AccountContext, c: Candidate) -> bool:
    """硬检查 + AI 质检；返回质检是否出错。"""
    c.issues = hard_check(c.title, c.body, c.tags, c.image_prompts, ctx.rules)
    try:
        await _evaluate(llm, ctx, c)
        return False
    except LLMError:
        logger.warning("质检失败", exc_info=True)
        return True


def _sig(title: str, body: str) -> str:
    import hashlib
    return hashlib.sha1(f"{title}\n{body}".encode()).hexdigest()[:12]


def _history(cands: list[Candidate], start: int = 1) -> list[dict]:
    return [{"attempt": start + i, "score": c.score,
             "problems": len(c.issues) + len(c.evaluation.get("violated_rules", []))} for i, c in enumerate(cands)]


async def _evaluate(llm: LLM, ctx: AccountContext, c: Candidate) -> None:
    data = await complete_json(llm, [
        {"role": "system", "content": prompts.EVALUATOR_SYSTEM},
        {"role": "user", "content": prompts.EVALUATOR_USER.format(
            profile=ctx.profile_text(),
            rules=ctx.rules_text(),
            title=c.title,
            body=c.body,
            body_len=body_len(c.body),
            tags="、".join(c.tags),
            images="\n".join(f"{i + 1}. {p}" for i, p in enumerate(c.image_prompts)) or "（无）",
        )},
    ], temperature=0.2)
    dims = {}
    for k in ("hook", "value", "voice", "fit", "rules"):
        try:
            dims[k] = max(0.0, min(10.0, float(data.get(k, 0))))
        except (TypeError, ValueError):
            dims[k] = 0.0
    # 分数由代码算，不信模型自己报的总分；规则没遵守直接封顶
    score = round(sum(dims.values()) / len(dims), 1)
    violated = [str(v) for v in data.get("violated_rules") or [] if str(v).strip()]
    if violated:
        score = min(score, 6.0)
    c.score = score
    c.evaluation = {
        "dimensions": dims,
        "violated_rules": violated,
        "issues": [str(x) for x in data.get("issues") or []],
        "suggestions": [str(x) for x in data.get("suggestions") or []],
    }


def _feedback_for(c: Candidate, note: str = "") -> str:
    ev = c.evaluation
    lines = [f"- 用户的要求：{note.strip()}"] if note.strip() else []
    lines += [f"- 硬伤：{i}" for i in c.issues]
    lines += [f"- 没遵守规则：{r}" for r in ev.get("violated_rules", [])]
    lines += [f"- 问题：{i}" for i in ev.get("issues", [])]
    lines += [f"- 建议：{s}" for s in ev.get("suggestions", [])]
    return "\n".join(lines)


async def write_draft(
    session: Session,
    llm: LLM,
    account_id: str,
    *,
    topic_id: str | None = None,
    hint: str = "",
    trigger: Trigger = Trigger.manual,
    emit: Emit = _noop,
    fetch: Fetcher | None = None,
) -> Draft:
    ctx = load_context(session, account_id)
    if not (ctx.theme or ctx.keywords or hint or topic_id):
        raise ValueError("账号还没有设定主题，先和管家聊聊账号定位吧")

    topic = await _pick_topic(session, llm, ctx, topic_id, hint, emit, fetch)

    candidates: list[Candidate] = []
    eval_failed = False
    for attempt in range(1, MAX_ATTEMPTS + 1):
        base = max(candidates, key=lambda x: x.rank()) if candidates else None
        emit("write", "第 1 版写作中…" if base is None else f"按质检意见改第 {attempt - 1} 轮…", {"attempt": attempt})
        try:
            c = (await _generate(llm, ctx, topic, hint, "") if base is None
                 else await _revise(llm, ctx, base, _feedback_for(base)))
        except LLMError as e:
            if candidates:
                emit("warning", f"第 {attempt} 版生成失败（{e}），使用已有的最好版本", None)
                break
            raise
        if await _check(llm, ctx, c):
            eval_failed = True
            emit("warning", "质检服务出错，这一版没有经过 AI 质检", None)
        candidates.append(c)
        problems = len(c.issues) + len(c.evaluation.get("violated_rules", []))
        emit("review", f"{'第 1 版' if base is None else f'改第 {attempt - 1} 轮'}："
             f"{c.score if c.score is not None else '未评分'} 分" + (f"，还有 {problems} 处要改" if problems else ""),
             {"attempt": attempt, "score": c.score, "issues": c.issues, "evaluation": c.evaluation})
        if c.passed:
            break

    best = max(candidates, key=lambda x: x.rank())
    needs_attention = bool(best.issues) or best.score is None or best.score < PASS_SCORE or eval_failed
    if needs_attention:
        emit("warning", "没有一版完全达标，已保存最好的一版，并标记为需要重点检查", None)

    best.evaluation = {**best.evaluation, "history": _history(candidates), "checked": _sig(best.title, best.body)}
    draft = Draft(
        user_id=ctx.user_id,
        account_id=ctx.account_id,
        topic_id=topic.id,
        title=best.title,
        body=best.body,
        tags=best.tags,
        original_title=best.title,
        original_body=best.body,
        trigger=trigger,
        score=best.score,
        evaluation=best.evaluation,
        check_issues=best.issues,
        attempts=len(candidates),
        needs_attention=needs_attention,
    )
    session.add(draft)
    session.flush()
    status = ImageStatus.pending if get_settings().image_configured else ImageStatus.skipped
    for i, p in enumerate(best.image_prompts):
        session.add(DraftImage(draft_id=draft.id, idx=i, prompt=p, status=status))
    topic.status = TopicStatus.used
    session.add(topic)
    draft.updated_at = utcnow()
    session.commit()
    session.refresh(draft)
    emit("done", f"草稿已保存：{draft.title}", {"draft_id": draft.id, "score": draft.score})
    return draft


async def revise_draft(session: Session, llm: LLM, draft_id: str, *, note: str = "", emit: Emit = _noop,
                       rounds: int = 2) -> Draft:
    """按当前质检意见（和用户补充的要求）在草稿上再改 1-2 轮，改好了才替换；没改好保留原稿。"""
    draft = session.get(Draft, draft_id)
    if draft is None:
        raise LookupError("草稿不存在")
    ctx = load_context(session, draft.account_id)
    images = sorted(session.exec(select(DraftImage).where(DraftImage.draft_id == draft.id)).all(), key=lambda i: i.idx)
    cur = Candidate(title=draft.title, body=draft.body, tags=list(draft.tags), image_prompts=[i.prompt for i in images],
                    issues=list(draft.check_issues), evaluation=dict(draft.evaluation or {}), score=draft.score)
    if note.strip() or cur.score is None or cur.evaluation.get("checked") != _sig(cur.title, cur.body):
        # 用户改过稿子或提了新要求：先按现在的版本重新质检，意见才对得上
        await _check(llm, ctx, cur)
    history = list((draft.evaluation or {}).get("history") or [])
    start = (history[-1]["attempt"] + 1) if history else draft.attempts + 1
    tried: list[Candidate] = []
    best = cur
    for r in range(rounds):
        emit("write", f"按质检意见再改第 {r + 1} 轮…", {"attempt": start + r})
        try:
            c = await _revise(llm, ctx, best, _feedback_for(best, note if r == 0 else ""))
        except LLMError as e:
            if tried:
                emit("warning", f"这一轮没改成（{e}），用已经改好的版本", None)
                break
            raise
        await _check(llm, ctx, c)
        tried.append(c)
        problems = len(c.issues) + len(c.evaluation.get("violated_rules", []))
        emit("review", f"改第 {r + 1} 轮：{c.score if c.score is not None else '未评分'} 分"
             + (f"，还有 {problems} 处要改" if problems else ""), {"score": c.score})
        if c.rank() > best.rank():
            best = c
        if c.passed:
            break
    history += _history(tried, start)
    improved = best is not cur
    if improved:
        draft.title, draft.body, draft.tags = best.title, best.body, best.tags
        for i, img in enumerate(images):
            if i < len(best.image_prompts) and img.prompt != best.image_prompts[i] and img.status != ImageStatus.done:
                img.prompt = best.image_prompts[i]
                session.add(img)
    draft.score, draft.check_issues = best.score, best.issues
    draft.evaluation = {**best.evaluation, "history": history, "checked": _sig(best.title, best.body)}
    draft.attempts += len(tried)
    draft.needs_attention = not best.passed
    draft.updated_at = utcnow()
    session.add(draft)
    session.commit()
    session.refresh(draft)
    emit("done", ("改好了：" if improved else "这几轮没比原稿更好，保留原稿：") + f"{draft.score} 分", {"draft_id": draft.id})
    return draft
