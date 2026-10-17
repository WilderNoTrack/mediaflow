"""从用户的修改和反馈里学口味：对比原稿和改后版本，提炼成候选规则。

候选规则不会自动生效，要用户在界面上确认，避免一次随手改动把账号带偏。
"""

from __future__ import annotations

from sqlmodel import Session, col, select

from mediaflow.agents import prompts
from mediaflow.agents.context import load_context
from mediaflow.domain.models import Draft, Feedback
from mediaflow.llm.client import LLM, complete_json


async def suggest_rules(session: Session, llm: LLM, draft_id: str) -> dict:
    d = session.get(Draft, draft_id)
    if d is None:
        raise LookupError("草稿不存在")
    feedbacks = session.exec(
        select(Feedback).where(Feedback.draft_id == draft_id).order_by(col(Feedback.created_at))
    ).all()
    edited = d.title != d.original_title or d.body != d.original_body
    if not edited and not any(f.comment for f in feedbacks):
        return {"rules": [], "summary": "这篇没有修改也没有文字反馈，暂时没什么可学的"}
    ctx = load_context(session, d.account_id)
    data = await complete_json(llm, [
        {"role": "system", "content": prompts.LEARN_SYSTEM},
        {"role": "user", "content": prompts.LEARN_USER.format(
            profile=ctx.profile_text(), rules=ctx.rules_text(),
            orig_title=d.original_title, orig_body=d.original_body,
            title=d.title, body=d.body,
            feedback="\n".join(f"- [{'满意' if f.rating == 'good' else '不满意'}] {f.comment}" for f in feedbacks) or "（无）",
        )},
    ], temperature=0.3)
    existing = set(ctx.rules)
    rules = [str(r).strip() for r in data.get("rules") or [] if str(r).strip() and str(r).strip() not in existing]
    return {"rules": rules[:5], "summary": str(data.get("summary", ""))}
