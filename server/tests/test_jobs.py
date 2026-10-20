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

    async def one(self, model, prompt, refs=None):
        calls.append(model)
        if model == "gpt-image-2.5":
            raise images_mod.ImageError("生图失败：busy")
        return b"png"

    monkeypatch.setattr(images_mod.GrsaiProvider, "_one", one)
    p = images_mod.GrsaiProvider(key="k", model="gpt-image-2.5")
    assert await p.generate("x") == b"png" and calls == ["gpt-image-2.5", "nano-banana-2.1"]

    async def bad(self, model, prompt, refs=None):
        calls.append(model)
        raise images_mod.ImageError("违规", retryable=False)

    calls.clear()
    monkeypatch.setattr(images_mod.GrsaiProvider, "_one", bad)
    with pytest.raises(images_mod.ImageError):
        await images_mod.GrsaiProvider(key="k").generate("x")
    assert calls == ["gpt-image-2.5"]
    assert images_mod._payload("nano-banana-2.1") == {"aspectRatio": "3:4", "imageSize": "1K"}


async def test_images_mold_reference_post(session, llm, account, with_images, monkeypatch):
    """写稿时挑一篇对标爆款当参考帖，原图缓存到本地；出图一张对一张照着原帖那张做。"""
    import io

    from PIL import Image

    from mediaflow.domain.models import Benchmark, BenchmarkStatus
    from mediaflow.services import refpost as refpost_mod
    from mediaflow.services import refs as refs_mod

    monkeypatch.setattr(refpost_mod, "cache_local", refs_mod.cache_local)  # 这条测试要真的走缓存
    got = []

    class Resp:
        def __init__(self, color):
            buf = io.BytesIO()
            Image.new("RGB", (60, 80), color).save(buf, "WEBP")
            self.content = buf.getvalue()

        def raise_for_status(self):
            pass

    async def fake_get(self, url, **kw):
        got.append(url)
        return Resp("red" if "c1" in url else "blue" if "i2" in url else "green")

    monkeypatch.setattr(refs_mod.httpx.AsyncClient, "get", fake_get)
    session.add(Benchmark(user_id=account.user_id, account_id=account.id, target="x", status=BenchmarkStatus.ready,
                          creator_name="程十安an",
                          samples=[{"title": "爆款", "likes": "1万", "kind": "图文", "cover": "https://ci/a/c1!webp",
                                    "images": ["https://ci/a/c1!webp", "https://ci/a/i2!webp", "https://ci/a/i3!webp"]},
                                   {"title": "视频", "likes": "9万", "kind": "视频", "cover": "https://ci/a/v!webp"}]))
    session.commit()
    llm.push("writer", post(images=["封面", "细节", "清单"])).push("eval", evaluation(8))
    job = enqueue(session, JobKind.write_draft, user_id="local", account_id=account.id, payload={})
    await run_job(job.id)
    d = session.exec(select(Draft)).one()
    assert d.reference["title"] == "爆款" and d.reference["creator"] == "程十安an"
    assert len(d.reference["local"]) == 3 and "https://ci/a/v!webp" not in got  # 视频笔记不参考
    assert "参考帖有 3 张图" in llm.prompts_of("writer")[0]

    img_job = session.exec(select(Job).where(Job.kind == JobKind.generate_images)).one()
    await run_job(img_job.id)
    by_n = with_images.refs
    assert len(by_n) == 3 and all(len(r) == 1 and r[0].startswith("data:image/jpeg;base64,") for r in by_n)
    assert len({r[0] for r in by_n}) == 3  # 每张照着原帖不同的那张
    assert all("严格照着参考图" in p for p in llm.prompts_of("image"))
    session.expire_all()
    imgs = session.exec(select(DraftImage).where(DraftImage.draft_id == d.id).order_by(DraftImage.idx)).all()
    assert [i.ref_path for i in imgs] == d.reference["local"]


async def test_image_set_is_unified(session, llm, account, monkeypatch):
    """没有参考帖：整套用同一份视觉规范，先出封面、其余带上封面当风格参照；重出某一张沿用规范和封面。"""
    from mediaflow.agents import prompts
    from mediaflow.services.images import generate_images

    monkeypatch.setenv("IMAGE_API_KEY", "x")
    get_settings.cache_clear()
    fake = FakeImages()
    images_mod.set_provider_factory(lambda: fake)
    llm.push("writer", post(images=["封面大字", "第一步", "第二步"])).push("eval", evaluation(8))
    llm.push("image", {"spec": "奶油白底#F5EFE6、圆润粗黑体、同一个短发女生", "prompts": [
        {"idx": 1, "prompt": "封面：大字「3步」"}, {"idx": 2, "prompt": "第一步特写"}, {"idx": 3, "prompt": "第二步特写"}]})
    job = enqueue(session, JobKind.write_draft, user_id="local", account_id=account.id, payload={})
    await run_job(job.id)
    d = session.exec(select(Draft)).one()
    assert d.reference == {}
    await generate_images(session, llm, d.id)
    session.refresh(d)
    assert d.image_spec.startswith("奶油白底")
    assert len(llm.prompts_of("image")) == 1  # 一整套一次写，不是每张各写各的
    assert fake.refs[0] is None and all(r and len(r) == 1 for r in fake.refs[1:])  # 封面先出，其余带封面
    imgs = session.exec(select(DraftImage).where(DraftImage.draft_id == d.id).order_by(DraftImage.idx)).all()
    assert all("奶油白底#F5EFE6" in i.expanded_prompt for i in imgs)
    assert "同一套里已经出好的第 1 张" in imgs[2].expanded_prompt and imgs[0].status == ImageStatus.done

    llm.push("image", {"spec": "完全不同的新规范", "prompts": [{"idx": 3, "prompt": "第二步重画"}]})
    await generate_images(session, llm, d.id, only_idx=2)
    session.refresh(d)
    assert d.image_spec.startswith("奶油白底")  # 只重出一张：规范沿用，不让模型改
    assert prompts.IMAGE_SPEC_FIXED.split("\n")[1][:10] in llm.prompts_of("image")[-1]
    assert len(fake.refs[-1]) == 1 and fake.refs[-1][0] == fake.refs[1][0]  # 还是拿封面当参照


async def test_mold_regen_one_keeps_style(session, llm, account, monkeypatch):
    """照着参考帖出：重出某一张时带两张参考图（原帖那张当版式模板 + 同套封面当风格参照）。"""
    import io

    from PIL import Image

    from mediaflow.services.images import generate_images

    monkeypatch.setenv("IMAGE_API_KEY", "x")
    get_settings.cache_clear()
    fake = FakeImages()
    images_mod.set_provider_factory(lambda: fake)
    d_dir = get_settings().images_dir / "_refs"
    d_dir.mkdir(parents=True, exist_ok=True)
    for n in ("a", "b"):
        buf = io.BytesIO()
        Image.new("RGB", (30, 40), "red").save(buf, "JPEG")
        (d_dir / f"{n}.jpg").write_bytes(buf.getvalue())
    d = Draft(user_id="local", account_id=account.id, title="t", body="b", original_title="t", original_body="b",
              reference={"title": "原帖", "local": ["_refs/a.jpg", "_refs/b.jpg"]})
    session.add(d)
    session.commit()
    session.add_all([DraftImage(draft_id=d.id, idx=k, prompt=f"第{k}张") for k in range(3)])
    session.commit()
    await generate_images(session, llm, d.id)
    assert all(len(r) == 1 for r in fake.refs)  # 整套一起出：每张只带原帖对应那张
    await generate_images(session, llm, d.id, only_idx=2)
    assert len(fake.refs[-1]) == 2
    img = session.exec(select(DraftImage).where(DraftImage.draft_id == d.id, DraftImage.idx == 2)).one()
    assert img.ref_path == "_refs/b.jpg" and img.expanded_prompt.startswith("参考图 1 是版式模板")
