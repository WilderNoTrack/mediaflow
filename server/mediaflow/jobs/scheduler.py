"""自动模式调度：定期检查哪些账号到点了，排一个写稿任务。写好的稿子进待审核。"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from sqlmodel import Session, select

from mediaflow.db import session_scope
from mediaflow.domain.models import Account, AutoFrequency, JobKind, Trigger, utcnow
from mediaflow.jobs.queue import JobConflict, enqueue

logger = logging.getLogger(__name__)

INTERVALS = {
    AutoFrequency.daily: timedelta(days=1),
    AutoFrequency.every_2_days: timedelta(days=2),
    AutoFrequency.weekly: timedelta(days=7),
}


def is_due(acc: Account, now: datetime) -> bool:
    if not acc.auto_enabled:
        return False
    if acc.last_auto_run_at is None:
        return True
    return now - acc.last_auto_run_at >= INTERVALS[acc.auto_frequency]


def tick(session: Session, now: datetime | None = None) -> list[str]:
    now = now or utcnow()
    started = []
    for acc in session.exec(select(Account).where(Account.auto_enabled == True)).all():  # noqa: E712
        if not is_due(acc, now):
            continue
        try:
            enqueue(session, JobKind.write_draft, user_id=acc.user_id, account_id=acc.id,
                    payload={"trigger": Trigger.auto.value})
        except JobConflict:
            continue
        acc.last_auto_run_at = now
        session.add(acc)
        session.commit()
        started.append(acc.id)
        logger.info("[自动模式] 账号「%s」到点，已排写稿任务", acc.name)
    return started


async def scheduler_loop(interval: int = 60) -> None:
    while True:
        try:
            with session_scope() as s:
                tick(s)
        except Exception:  # noqa: BLE001
            logger.exception("[自动模式] 调度出错")
        await asyncio.sleep(interval)
