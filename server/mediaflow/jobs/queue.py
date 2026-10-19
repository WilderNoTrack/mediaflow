"""后台任务队列（数据库持久化，进程内 asyncio worker）。

- 写稿、配图都是 Job：有状态、有进度事件、失败原因可查，前端轮询展示。
- 同一账号同时只允许一个写稿任务（数据库层面检查，不依赖进程内锁）。
- 程序重启时，上次没跑完的任务标记为失败，不会卡在「运行中」。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from sqlmodel import Session, col, select

from mediaflow.db import session_scope
from mediaflow.domain.models import (
    DraftImage, ImageStatus, Job, JobKind, JobStatus, Trigger, utcnow,
)

logger = logging.getLogger(__name__)

ACTIVE = (JobStatus.queued, JobStatus.running)


class JobConflict(RuntimeError):
    def __init__(self, job: Job) -> None:
        msg = {JobKind.clone_creator: "这个账号正在拆解对标账号，等它好了再来",
               JobKind.find_benchmarks: "正在找对标候选，等这一轮找完再来",
               JobKind.revise_draft: "这篇正在按质检意见修改，稍等一下"}.get(job.kind, "这个账号已经有一篇正在写，等它写完再来")
        super().__init__(msg)
        self.job = job


def active_write_job(session: Session, account_id: str, kind: JobKind = JobKind.write_draft) -> Job | None:
    return session.exec(
        select(Job).where(
            Job.account_id == account_id,
            Job.kind == kind,
            col(Job.status).in_(ACTIVE),
        )
    ).first()


def enqueue(session: Session, kind: JobKind, *, user_id: str, account_id: str | None, payload: dict) -> Job:
    if kind in (JobKind.write_draft, JobKind.clone_creator, JobKind.find_benchmarks, JobKind.revise_draft) and account_id:
        existing = active_write_job(session, account_id, kind)
        if existing:
            raise JobConflict(existing)
    job = Job(kind=kind, user_id=user_id, account_id=account_id, payload=payload)
    session.add(job)
    session.commit()
    session.refresh(job)
    _wake.set()
    return job


def _emitter(job_id: str) -> Callable[[str, str, dict | None], None]:
    def emit(stage: str, message: str, data: dict | None = None) -> None:
        with session_scope() as s:
            job = s.get(Job, job_id)
            if job is None:
                return
            job.events = [*job.events, {"at": utcnow().isoformat(), "stage": stage, "message": message, "data": data or {}}]
            s.add(job)
            s.commit()
    return emit


# ─── 任务处理器 ──────────────────────────────────────────────────────────────

Handler = Callable[[Job, Callable[..., None]], Awaitable[dict[str, Any]]]


async def _handle_write(job: Job, emit) -> dict:
    from mediaflow.agents.pipeline import write_draft
    from mediaflow.llm.client import get_llm

    llm = get_llm()
    with session_scope() as s:
        draft = await write_draft(
            s, llm, job.account_id or "",
            topic_id=job.payload.get("topic_id"),
            hint=job.payload.get("hint", ""),
            trigger=Trigger(job.payload.get("trigger", "manual")),
            emit=emit,
        )
        pending = s.exec(select(DraftImage).where(
            DraftImage.draft_id == draft.id, DraftImage.status == ImageStatus.pending
        )).first()
        if pending:
            enqueue(s, JobKind.generate_images, user_id=job.user_id,
                    account_id=job.account_id, payload={"draft_id": draft.id})
        return {"draft_id": draft.id, "title": draft.title, "score": draft.score}


async def _handle_images(job: Job, emit) -> dict:
    from mediaflow.llm.client import get_llm
    from mediaflow.services.images import generate_images

    with session_scope() as s:
        return await generate_images(
            s, get_llm(), job.payload["draft_id"], only_idx=job.payload.get("only_idx"), emit=emit,
        )


async def _handle_clone(job: Job, emit) -> dict:
    from mediaflow.llm.client import get_llm
    from mediaflow.services import benchmark

    p = job.payload
    ids = p.get("benchmark_ids") or ([p["benchmark_id"]] if p.get("benchmark_id") else [])
    with session_scope() as s:
        return await benchmark.run(s, get_llm(), job.account_id or "", ids, p.get("theme") or "", emit=emit)


async def _handle_find(job: Job, emit) -> dict:
    from mediaflow.llm.client import get_llm
    from mediaflow.services import benchmark

    p = job.payload
    with session_scope() as s:
        return await benchmark.run_find(s, get_llm(), job.account_id or "", p.get("query") or "", p.get("prefer") or "",
                                        emit=emit)


async def _handle_revise(job: Job, emit) -> dict:
    from mediaflow.agents.pipeline import revise_draft
    from mediaflow.llm.client import get_llm

    with session_scope() as s:
        d = await revise_draft(s, get_llm(), job.payload["draft_id"], note=job.payload.get("note", ""), emit=emit)
        return {"draft_id": d.id, "score": d.score}


HANDLERS: dict[JobKind, Handler] = {
    JobKind.write_draft: _handle_write,
    JobKind.generate_images: _handle_images,
    JobKind.clone_creator: _handle_clone,
    JobKind.find_benchmarks: _handle_find,
    JobKind.revise_draft: _handle_revise,
}


async def run_job(job_id: str) -> None:
    with session_scope() as s:
        job = s.get(Job, job_id)
        if job is None or job.status != JobStatus.queued:
            return
        job.status, job.started_at = JobStatus.running, utcnow()
        s.add(job)
        s.commit()
        snapshot = Job.model_validate(job.model_dump())
    emit = _emitter(job_id)
    try:
        result = await HANDLERS[snapshot.kind](snapshot, emit)
        status, error = JobStatus.succeeded, ""
    except Exception as e:  # noqa: BLE001 - 任务失败要落库，不能吞
        logger.exception("任务 %s 失败", job_id)
        result, status, error = {}, JobStatus.failed, str(e) or type(e).__name__
        emit("error", error, None)
    with session_scope() as s:
        job = s.get(Job, job_id)
        if job:
            job.status, job.result, job.error, job.finished_at = status, result, error, utcnow()
            s.add(job)
            s.commit()


# ─── Worker ─────────────────────────────────────────────────────────────────

_wake = asyncio.Event()


def recover_interrupted() -> int:
    with session_scope() as s:
        stuck = s.exec(select(Job).where(Job.status == JobStatus.running)).all()
        for j in stuck:
            j.status, j.error, j.finished_at = JobStatus.failed, "程序重启，任务被中断", utcnow()
            s.add(j)
        from mediaflow.domain.models import Benchmark, BenchmarkStatus, DraftImage, ImageStatus
        # 出图出到一半重启：没有排队任务接手的配图标成失败，不然草稿页会一直转圈
        queued = {j.payload.get("draft_id") for j in s.exec(select(Job).where(
            Job.kind == JobKind.generate_images, Job.status == JobStatus.queued)).all()}
        for img in s.exec(select(DraftImage).where(col(DraftImage.status).in_((ImageStatus.pending, ImageStatus.running)))).all():
            if img.status == ImageStatus.running or img.draft_id not in queued:
                img.status, img.error = ImageStatus.failed, "程序重启，这张没出完，点重新生成就好"
                img.updated_at = utcnow()
                s.add(img)
        for b in s.exec(select(Benchmark).where(Benchmark.status == BenchmarkStatus.analyzing)).all():
            b.status, b.error = BenchmarkStatus.failed, "程序重启，拆解被中断，重新试一次就好"
            s.add(b)
        s.commit()
        return len(stuck)


async def worker_loop(concurrency: int = 2) -> None:
    sem = asyncio.Semaphore(concurrency)
    running: set[str] = set()

    async def _run(jid: str) -> None:
        try:
            await run_job(jid)
        finally:
            running.discard(jid)
            sem.release()

    while True:
        with session_scope() as s:
            queued = s.exec(
                select(Job.id).where(Job.status == JobStatus.queued).order_by(col(Job.created_at))
            ).all()
        for jid in queued:
            if jid in running:
                continue
            await sem.acquire()
            running.add(jid)
            asyncio.create_task(_run(jid))
        _wake.clear()
        try:
            await asyncio.wait_for(_wake.wait(), timeout=2)
        except TimeoutError:
            pass
