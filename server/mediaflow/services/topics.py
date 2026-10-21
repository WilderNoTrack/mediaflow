"""选题：抓热点 → 模型按账号定位出选题 → 去重 → 存进账号选题库。"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlmodel import Session, select

from mediaflow.agents import prompts
from mediaflow.agents.checks import is_duplicate
from mediaflow.agents.context import AccountContext
from mediaflow.domain.models import Topic, TopicStatus
from mediaflow.llm.client import LLM, complete_json
from mediaflow.sources.base import SourceReport
from mediaflow.sources.registry import fetch_all

Fetcher = Callable[[str, int], Awaitable[SourceReport]]


@dataclass
class TopicProposal:
    topics: list[Topic]
    report: SourceReport
    skipped_duplicates: int

    @property
    def source_note(self) -> str:
        failed = self.report.failed_labels
        if not self.report.enabled:
            return "没有可用的热点来源，本次选题完全由 AI 根据账号定位构思" if self.report.statuses else ""
        if len(failed) == len(self.report.enabled):
            return "所有热点来源都没抓到数据，本次选题完全由 AI 根据账号定位构思"
        if failed:
            return f"{'、'.join(failed)} 没抓到数据，其余来源正常"
        return ""


def _search_keyword(ctx: AccountContext, direction: str) -> str:
    return direction or (ctx.keywords[0] if ctx.keywords else "") or ctx.theme


async def propose_topics(
    session: Session,
    llm: LLM,
    ctx: AccountContext,
    *,
    direction: str = "",
    count: int = 5,
    fetch: Fetcher | None = None,
) -> TopicProposal:
    fetch = fetch or (lambda kw, n: fetch_all(kw, n))
    report = await fetch(_search_keyword(ctx, direction), 8)
    external = "\n".join(
        f"- [{it.source}] {it.title}" + (f"（热度 {it.heat}）" if it.heat else "")
        for it in report.items[:40]
    ) or "（本次没有抓到外部热点）"
    history = list(ctx.recent_titles[:20]) + list(ctx.used_topics[:20])
    data = await complete_json(llm, [
        {"role": "system", "content": prompts.TOPIC_SYSTEM},
        {"role": "user", "content": prompts.TOPIC_USER.format(
            profile=ctx.profile_text(),
            rules=ctx.rules_text(),
            history="\n".join(f"- {t}" for t in history) or "（暂无）",
            direction_block=f"【用户指定方向】{direction}\n\n" if direction else "",
            untrusted_notice=prompts.UNTRUSTED_NOTICE,
            external=external,
            count=count + 2,  # 多要两个，去重后仍够数
        )},
    ], temperature=0.9)

    existing_new = session.exec(
        select(Topic.title).where(Topic.account_id == ctx.account_id, Topic.status == TopicStatus.new)
    ).all()
    seen = history + list(existing_new)
    saved: list[Topic] = []
    dup = 0
    for raw in data.get("topics", []):
        title = str(raw.get("title", "")).strip()
        if not title:
            continue
        if is_duplicate(title, seen):
            dup += 1
            continue
        t = Topic(
            user_id=ctx.user_id,
            account_id=ctx.account_id,
            title=title[:80],
            angle=str(raw.get("angle", ""))[:200],
            reason=str(raw.get("reason", ""))[:200],
            source=str(raw.get("source", "ai"))[:20] or "ai",
            source_url=str(raw.get("source_url", ""))[:500],
        )
        session.add(t)
        saved.append(t)
        seen.append(title)
        if len(saved) >= count:
            break
    session.commit()
    return TopicProposal(topics=saved, report=report, skipped_duplicates=dup)


def report_to_dict(report: SourceReport) -> list[dict]:
    return [json.loads(json.dumps(s.__dict__, ensure_ascii=False)) for s in report.statuses]
