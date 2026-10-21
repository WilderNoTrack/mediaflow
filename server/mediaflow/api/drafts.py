from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlmodel import Session, col, select

from mediaflow.agents.checks import clean_tags, hard_check
from mediaflow.agents.learning import suggest_rules
from mediaflow.api.deps import owned_account, owned_draft
from mediaflow.db import get_session
from mediaflow.domain.models import (
    Account, Draft, DraftImage, DraftStatus, Feedback, ImageStatus, Job, JobKind, Topic, utcnow,
)
from mediaflow.domain.schemas import (
    DraftDetail, DraftOut, DraftPatch, FeedbackIn, ImageEditIn, ImageOut, JobOut, LearnOut, ReferenceIn, ReviseIn, WriteIn,
)
from mediaflow.jobs.queue import ACTIVE, enqueue
from mediaflow.llm.client import get_llm
from mediaflow.services.export import build_zip, post_text

router = APIRouter(tags=["drafts"])


def _img_url(img: DraftImage) -> str | None:
    return f"/files/images/{img.path}" if img.status == ImageStatus.done and img.path else None


def _images(s: Session, draft_id: str) -> list[DraftImage]:
    return list(s.exec(select(DraftImage).where(DraftImage.draft_id == draft_id).order_by(col(DraftImage.idx))).all())


def _out(s: Session, d: Draft, detail: bool = False) -> DraftOut | DraftDetail:
    imgs = _images(s, d.id)
    cover = next((_img_url(i) for i in imgs if _img_url(i)), None)
    base = {**d.model_dump(), "edited": d.title != d.original_title or d.body != d.original_body, "cover_url": cover,
            "images_total": len(imgs), "images_done": sum(i.status == ImageStatus.done for i in imgs),
            "images_busy": sum(i.status in (ImageStatus.pending, ImageStatus.running) for i in imgs)}
    if not detail:
        return DraftOut(**base)
    return DraftDetail(**base, images=[
        ImageOut(id=i.id, idx=i.idx, prompt=i.prompt, status=i.status, url=_img_url(i), error=i.error,
                 ref_url=_ref_url(d, i), page_type=i.page_type, review=i.review or {}, mode=i.mode, made_by=i.made_by,
                 layout=i.layout or {}, source={k: v for k, v in (i.source or {}).items() if k != "base"},
                 base_url=f"/files/images/{i.source['base']}" if (i.source or {}).get("base") else None) for i in imgs
    ])


def _ref_url(d: Draft, img: DraftImage) -> str | None:
    """已出的图记着照的是哪张；还没出的按「一张对一张」预告会照哪张。"""
    from mediaflow.services.images import mold_slot

    local = (d.reference or {}).get("local") or []
    if img.ref_path or d.image_mold == "template":
        rel = img.ref_path
    else:
        rel = local[mold_slot(local, img.idx)] if local else ""
    return f"/files/images/{rel}" if rel else None


@router.get("/api/accounts/{account_id}/drafts", response_model=list[DraftOut])
def list_drafts(status: DraftStatus | None = None, acc: Account = Depends(owned_account),
                s: Session = Depends(get_session)):
    q = select(Draft).where(Draft.account_id == acc.id)
    if status:
        q = q.where(Draft.status == status)
    return [_out(s, d) for d in s.exec(q.order_by(col(Draft.created_at).desc()).limit(200)).all()]


@router.post("/api/accounts/{account_id}/write", response_model=JobOut, status_code=202)
def start_writing(body: WriteIn, acc: Account = Depends(owned_account), s: Session = Depends(get_session)):
    job = enqueue(s, JobKind.write_draft, user_id=acc.user_id, account_id=acc.id,
                  payload={"topic_id": body.topic_id, "hint": body.hint, "trigger": "chat" if body.from_chat else "manual",
                           "reference_url": body.reference_url.strip(), "use_exemplar": body.use_exemplar,
                           "image_plan": [p.strip() for p in body.image_plan if p.strip()]})
    if body.from_chat:
        from mediaflow.agents.manager import log_tool

        t = s.get(Topic, body.topic_id) if body.topic_id else None
        args = {"topic_id": body.topic_id or ""} | ({"reference_url": body.reference_url.strip()} if body.reference_url.strip() else {})
        log_tool(s, acc, "write_post", args,
                 {"ok": True, "job_id": job.id, "topic": t.title if t else "",
                  "note": "用户点了「照这篇写」" if body.reference_url.strip() and not t else "用户点了「写这篇」"})
    return JobOut(**job.model_dump())


@router.put("/api/drafts/{draft_id}/reference", response_model=DraftDetail)
async def set_reference(body: ReferenceIn, d: Draft = Depends(owned_draft), s: Session = Depends(get_session)):
    """换配图照着的那篇参考帖：读这篇笔记、缓存原图。之后点「全部重新出」就照着它一张对一张出图（文案不动）。"""
    from mediaflow.services import refpost

    try:
        ref = await refpost.from_url(body.url)
    except refpost.RefError as e:
        raise HTTPException(400, str(e)) from e
    d.reference = {**ref, "extra": (d.reference or {}).get("extra") or []}  # 文案参考不动，只换配图照的那篇
    d.image_spec = ""  # 换了模板，下次出图重新定统一规范
    for i in _images(s, d.id):
        i.ref_path = ""
        s.add(i)
    d.updated_at = utcnow()
    s.add(d)
    s.commit()
    s.refresh(d)
    return _out(s, d, detail=True)


@router.get("/api/drafts/{draft_id}", response_model=DraftDetail)
def get_draft(d: Draft = Depends(owned_draft), s: Session = Depends(get_session)):
    return _out(s, d, detail=True)


@router.patch("/api/drafts/{draft_id}", response_model=DraftDetail)
def update_draft(body: DraftPatch, d: Draft = Depends(owned_draft), s: Session = Depends(get_session)):
    data = body.model_dump(exclude_unset=True)
    if "tags" in data and data["tags"] is not None:
        data["tags"] = clean_tags(data["tags"])
    for k, v in data.items():
        if v is not None:
            setattr(d, k, v)
    if {"title", "body", "tags"} & data.keys():
        from mediaflow.agents.context import load_context
        d.check_issues = hard_check(d.title, d.body, d.tags, [i.prompt for i in _images(s, d.id)],
                                    load_context(s, d.account_id).rules)
    d.updated_at = utcnow()
    s.add(d)
    s.commit()
    return _out(s, d, detail=True)


@router.post("/api/drafts/{draft_id}/revise", response_model=JobOut, status_code=202)
def revise(body: ReviseIn, d: Draft = Depends(owned_draft), s: Session = Depends(get_session)):
    """按当前质检意见（可以再补一句自己的要求）让 AI 在这篇上再改 1-2 轮；改得更好才替换，否则保留原稿。"""
    get_llm()
    job = enqueue(s, JobKind.revise_draft, user_id=d.user_id, account_id=d.account_id,
                  payload={"draft_id": d.id, "note": body.note.strip()})
    return JobOut(**job.model_dump())


@router.delete("/api/drafts/{draft_id}", status_code=204)
def delete_draft(d: Draft = Depends(owned_draft), s: Session = Depends(get_session)):
    from mediaflow.services import exemplar

    exemplar.forget_draft(s, d)
    for row in [*_images(s, d.id), *s.exec(select(Feedback).where(Feedback.draft_id == d.id)).all()]:
        s.delete(row)
    s.flush()
    s.delete(d)
    s.commit()


@router.post("/api/drafts/{draft_id}/feedback", status_code=201)
def add_feedback(body: FeedbackIn, d: Draft = Depends(owned_draft), s: Session = Depends(get_session)):
    s.add(Feedback(user_id=d.user_id, draft_id=d.id, rating=body.rating, comment=body.comment.strip()))
    if body.rating == "good" and d.status == DraftStatus.pending_review:
        d.status = DraftStatus.approved
        s.add(d)
    s.commit()
    return {"ok": True}


@router.post("/api/drafts/{draft_id}/learn", response_model=LearnOut)
async def learn(d: Draft = Depends(owned_draft), s: Session = Depends(get_session)):
    return LearnOut(**await suggest_rules(s, get_llm(), d.id))


@router.post("/api/drafts/{draft_id}/images", response_model=JobOut, status_code=202)
def regenerate_images(idx: int | None = None, all: bool = False, d: Draft = Depends(owned_draft),  # noqa: A002
                      s: Session = Depends(get_session)):
    """idx=某一张重出；不传 idx 补出没出好的；all=true 全部重出。"""
    imgs = _images(s, d.id)
    if idx is not None and not any(i.idx == idx for i in imgs):
        raise HTTPException(404, "没有这张图")
    busy = {i.idx for i in imgs if i.status in (ImageStatus.pending, ImageStatus.running)}
    running = next((j for j in s.exec(select(Job).where(Job.kind == JobKind.generate_images, col(Job.status).in_(ACTIVE))).all()
                    if j.payload.get("draft_id") == d.id), None)
    if running and (idx is None or idx in busy):
        # 已经在出了：别再派一个任务，不然同一张图会出两遍、扣两次额度
        return JobOut(**running.model_dump())
    for i in imgs:
        if idx is None or i.idx == idx:
            if idx is not None or all or i.status != ImageStatus.done:
                i.status = ImageStatus.pending
                s.add(i)
    s.commit()
    job = enqueue(s, JobKind.generate_images, user_id=d.user_id, account_id=d.account_id,
                  payload={"draft_id": d.id, "only_idx": idx})
    return JobOut(**job.model_dump())


@router.post("/api/drafts/{draft_id}/images/edit", response_model=DraftDetail)
def edit_images(body: ImageEditIn, d: Draft = Depends(owned_draft), s: Session = Depends(get_session)):
    """改配图：改描述 / 加一张 / 删一张 / 调顺序 / 照原描述重出 / 换做法 / 直接改代码排的字（编号按改之前的顺序）。
    改过的马上重出（改字的当场重排好，不用等），其余不动。"""
    from mediaflow.services import draft_edit

    try:
        res = draft_edit.apply_ops(s, d, [o.model_dump(exclude_none=True) for o in body.ops])
    except draft_edit.EditError as e:
        raise HTTPException(409 if "正在出图" in str(e) else 400, str(e)) from e
    if body.regenerate and res["changed"]:
        enqueue(s, JobKind.generate_images, user_id=d.user_id, account_id=d.account_id, payload={"draft_id": d.id})
    s.refresh(d)
    return _out(s, d, detail=True)


@router.get("/api/drafts/{draft_id}/text")
def export_text(d: Draft = Depends(owned_draft)):
    return {"text": post_text(d)}


@router.get("/api/drafts/{draft_id}/export")
def export_zip(d: Draft = Depends(owned_draft), s: Session = Depends(get_session)):
    from urllib.parse import quote

    data, name = build_zip(s, d.id)
    if d.status in (DraftStatus.pending_review, DraftStatus.approved):
        d.status = DraftStatus.exported
        s.add(d)
        s.commit()
    return Response(data, media_type="application/zip", headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"})
