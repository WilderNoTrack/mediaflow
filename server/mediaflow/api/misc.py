import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlmodel import Session, col, select

from mediaflow import __version__
from mediaflow.agents import manager
from mediaflow.api.deps import current_user_id, owned_account
from mediaflow.config import get_settings
from mediaflow.db import get_session
from mediaflow.domain.models import Account, ChatMessage, Job
from mediaflow.domain.schemas import ChatIn, ChatMessageOut, CreatorOut, JobOut, SystemStatus
from mediaflow.llm.client import get_llm
from mediaflow.llm.client import llm_configured
from mediaflow.services import auth
from mediaflow.services.images import image_configured

router = APIRouter(tags=["misc"])


@router.get("/api/system", response_model=SystemStatus)
def system_status():
    s = get_settings()
    return SystemStatus(version=__version__, llm_configured=llm_configured(),
                        image_configured=image_configured(),
                        weibo_cookie_configured=bool(s.weibo_cookie), data_dir=str(s.data_dir))


@router.get("/api/accounts/{account_id}/chat", response_model=list[ChatMessageOut])
def chat_history(acc: Account = Depends(owned_account), s: Session = Depends(get_session)):
    rows = s.exec(select(ChatMessage).where(ChatMessage.account_id == acc.id)
                  .order_by(col(ChatMessage.created_at)).limit(500)).all()
    return [ChatMessageOut(**m.model_dump()) for m in rows]


@router.post("/api/accounts/{account_id}/chat", response_model=list[ChatMessageOut])
async def send_chat(body: ChatIn, acc: Account = Depends(owned_account), s: Session = Depends(get_session)):
    auth.check_quota(s, acc.user_id, "chats")
    msgs = await manager.chat(s, get_llm(), acc.id, body.text.strip(), draft_id=body.draft_id)
    return [ChatMessageOut(**m.model_dump()) for m in msgs]


@router.post("/api/accounts/{account_id}/chat/stream")
async def stream_chat(body: ChatIn, acc: Account = Depends(owned_account), s: Session = Depends(get_session)):
    """和 POST /chat 一样，但用 SSE 边做边推事件（见 manager.chat_events）。断开连接不影响这一轮跑完、存好。"""
    auth.check_quota(s, acc.user_id, "chats")
    q = manager.start_chat(get_llm(), acc.id, body.text.strip(), draft_id=body.draft_id)

    async def events():
        while True:
            try:
                ev = await asyncio.wait_for(q.get(), timeout=15)
            except TimeoutError:
                yield ": ping\n\n"  # 工具跑得久时保活，免得代理断开
                continue
            if ev is None:
                return
            yield f"data: {json.dumps(ev, ensure_ascii=False, default=str)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


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


@router.get("/api/research/creators", response_model=list[CreatorOut])
async def find_creators(q: str, platform: str = "xiaohongshu"):
    """按名字或领域关键词搜博主，用于挑对标账号。按粉丝从高到低。"""
    from mediaflow.research import service as research
    from mediaflow.research.types import Unsupported, count_num

    try:
        fn = research._need(platform, "search_creators", "搜博主")
        found = await research._throttled(platform, ("sc", platform, q.strip(), 10), lambda: fn(q.strip(), 10))
    except Unsupported as e:
        raise HTTPException(400, str(e)) from e
    except RuntimeError as e:
        raise HTTPException(502, str(e)) from e
    found = sorted(found, key=lambda c: -count_num(c.fans))
    return [CreatorOut(name=c.name, fans=c.fans, posts=c.posts, desc=c.desc, url=c.url) for c in found]
