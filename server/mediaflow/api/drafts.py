from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlmodel import Session, col, select

from mediaflow.agents.checks import clean_tags, hard_check
from mediaflow.agents.learning import suggest_rules
from mediaflow.api.deps import owned_account, owned_draft
from mediaflow.db import get_session
from mediaflow.domain.models import (
    Account, Draft, DraftImage, DraftStatus, Feedback, ImageStatus, JobKind, utcnow,
)
from mediaflow.domain.schemas import (
    DraftDetail, DraftOut, DraftPatch, FeedbackIn, ImageOut, JobOut, LearnOut, ReviseIn, WriteIn,
)
from mediaflow.jobs.queue import enqueue
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
    base = {**d.model_dump(), "edited": d.title != d.original_title or d.body != d.original_body, "cover_url": cover}
    if not detail:
        return DraftOut(**base)
    return DraftDetail(**base, images=[
        ImageOut(id=i.id, idx=i.idx, prompt=i.prompt, status=i.status, url=_img_url(i), error=i.error) for i in imgs
    ])


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
                  payload={"topic_id": body.topic_id, "hint": body.hint, "trigger": "manual"})
    return JobOut(**job.model_dump())


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
def regenerate_images(idx: int | None = None, d: Draft = Depends(owned_draft), s: Session = Depends(get_session)):
    imgs = _images(s, d.id)
    if idx is not None and not any(i.idx == idx for i in imgs):
        raise HTTPException(404, "没有这张图")
    for i in imgs:
        if idx is None or i.idx == idx:
            if idx is not None or i.status != ImageStatus.done:
                i.status = ImageStatus.pending
                s.add(i)
    s.commit()
    job = enqueue(s, JobKind.generate_images, user_id=d.user_id, account_id=d.account_id,
                  payload={"draft_id": d.id, "only_idx": idx})
    return JobOut(**job.model_dump())


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
