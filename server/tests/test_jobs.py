from datetime import timedelta

import pytest
from sqlmodel import Session, select

from mediaflow.config import get_settings
from mediaflow.domain.models import (
    Account, AutoFrequency, Draft, DraftImage, ImageStatus, Job, JobKind, JobStatus, utcnow,
)
from mediaflow.jobs import scheduler
from mediaflow.jobs.queue import JobConflict, enqueue, recover_interrupted, run_job
from mediaflow.services import images as images_mod
from tests.fakes import FakeImages, evaluation, post


@pytest.fixture
def with_images(monkeypatch):
    monkeypatch.setenv("IMAGE_API_KEY", "x")
    get_settings.cache_clear()
    fake = FakeImages(fail_idx={1})
    images_mod.set_provider_factory(lambda: fake)
    return fake


async def test_write_job_end_to_end_with_images(session, llm, account, with_images):
    llm.push("writer", post(images=["封面", "细节", "氛围"])).push("eval", evaluation(8))
    job = enqueue(session, JobKind.write_draft, user_id="local", account_id=account.id, payload={})
    await run_job(job.id)

    session.expire_all()
    job = session.get(Job, job.id)
    assert job.status == JobStatus.succeeded, job.error
    assert [e["stage"] for e in job.events][-1] == "done"
    draft = session.get(Draft, job.result["draft_id"])
    img_job = session.exec(select(Job).where(Job.kind == JobKind.generate_images)).one()
    await run_job(img_job.id)

    session.expire_all()
    imgs = session.exec(select(DraftImage).where(DraftImage.draft_id == draft.id).order_by(DraftImage.idx)).all()
    assert [i.status for i in imgs] == [ImageStatus.done, ImageStatus.failed, ImageStatus.done]
    assert imgs[1].error and imgs[0].expanded_prompt
    assert (get_settings().images_dir / imgs[0].path).exists()


async def test_failed_job_records_error(session, llm):
    a = Account(user_id="local", name="空号")
    session.add(a)
    session.commit()
    job = enqueue(session, JobKind.write_draft, user_id="local", account_id=a.id, payload={})
    await run_job(job.id)
    session.expire_all()
    job = session.get(Job, job.id)
    assert job.status == JobStatus.failed and "主题" in job.error


def test_one_write_job_per_account(session, account):
    enqueue(session, JobKind.write_draft, user_id="local", account_id=account.id, payload={})
    with pytest.raises(JobConflict):
        enqueue(session, JobKind.write_draft, user_id="local", account_id=account.id, payload={})


def test_recover_interrupted(session, account):
    j = Job(user_id="local", account_id=account.id, kind=JobKind.write_draft, status=JobStatus.running)
    session.add(j)
    session.commit()
    assert recover_interrupted() == 1
    session.expire_all()
    assert session.get(Job, j.id).status == JobStatus.failed


def test_scheduler_respects_frequency(fresh_db, account):
    with Session(fresh_db) as s:
        acc = s.get(Account, account.id)
        acc.auto_enabled, acc.auto_frequency = True, AutoFrequency.every_2_days
        acc.last_auto_run_at = utcnow() - timedelta(days=1)
        s.add(acc)
        s.commit()
        assert scheduler.tick(s) == []
        assert scheduler.tick(s, now=utcnow() + timedelta(days=1, minutes=1)) == [account.id]
        # 已经有写稿任务在排队，不会重复排
        acc = s.get(Account, account.id)
        acc.last_auto_run_at = None
        s.add(acc)
        s.commit()
        assert scheduler.tick(s) == []
        job = s.exec(select(Job)).one()
        assert job.payload["trigger"] == "auto"


async def test_grsai_falls_back_to_other_model(monkeypatch):
    calls = []

    async def one(self, model, prompt):
        calls.append(model)
        if model == "gpt-image-2.5":
            raise images_mod.ImageError("生图失败：busy")
        return b"png"

    monkeypatch.setattr(images_mod.GrsaiProvider, "_one", one)
    p = images_mod.GrsaiProvider(key="k", model="gpt-image-2.5")
    assert await p.generate("x") == b"png" and calls == ["gpt-image-2.5", "nano-banana-2.1"]

    async def bad(self, model, prompt):
        calls.append(model)
        raise images_mod.ImageError("违规", retryable=False)

    calls.clear()
    monkeypatch.setattr(images_mod.GrsaiProvider, "_one", bad)
    with pytest.raises(images_mod.ImageError):
        await images_mod.GrsaiProvider(key="k").generate("x")
    assert calls == ["gpt-image-2.5"]
    assert images_mod._payload("nano-banana-2.1") == {"aspectRatio": "3:4", "imageSize": "1K"}
