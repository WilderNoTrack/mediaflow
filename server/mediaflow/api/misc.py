from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, col, select

from mediaflow import __version__
from mediaflow.agents import manager
from mediaflow.api.deps import current_user_id, owned_account
from mediaflow.config import get_settings
from mediaflow.db import get_session
from mediaflow.domain.models import Account, ChatMessage, Job
from mediaflow.domain.schemas import ChatIn, ChatMessageOut, JobOut, SystemStatus
from mediaflow.llm.client import get_llm

router = APIRouter(tags=["misc"])


@router.get("/api/system", response_model=SystemStatus)
def system_status():
    s = get_settings()
    return SystemStatus(version=__version__, llm_configured=s.llm_configured,
                        image_configured=s.image_configured,
                        weibo_cookie_configured=bool(s.weibo_cookie), data_dir=str(s.data_dir))


@router.get("/api/accounts/{account_id}/chat", response_model=list[ChatMessageOut])
def chat_history(acc: Account = Depends(owned_account), s: Session = Depends(get_session)):
    rows = s.exec(select(ChatMessage).where(ChatMessage.account_id == acc.id)
                  .order_by(col(ChatMessage.created_at)).limit(500)).all()
    return [ChatMessageOut(**m.model_dump()) for m in rows]


@router.post("/api/accounts/{account_id}/chat", response_model=list[ChatMessageOut])
async def send_chat(body: ChatIn, acc: Account = Depends(owned_account), s: Session = Depends(get_session)):
    msgs = await manager.chat(s, get_llm(), acc.id, body.text.strip())
    return [ChatMessageOut(**m.model_dump()) for m in msgs]


@router.get("/api/jobs", response_model=list[JobOut])
def list_jobs(account_id: str | None = None, active: bool = False, s: Session = Depends(get_session),
              uid: str = Depends(current_user_id)):
    q = select(Job).where(Job.user_id == uid)
    if account_id:
        q = q.where(Job.account_id == account_id)
    if active:
        q = q.where(col(Job.status).in_(["queued", "running"]))
    return [JobOut(**j.model_dump()) for j in s.exec(q.order_by(col(Job.created_at).desc()).limit(30)).all()]


@router.get("/api/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: str, s: Session = Depends(get_session), uid: str = Depends(current_user_id)):
    j = s.get(Job, job_id)
    if j is None or j.user_id != uid:
        raise HTTPException(404, "任务不存在")
    return JobOut(**j.model_dump())
