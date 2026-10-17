from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, col, select

from mediaflow.agents.context import load_context
from mediaflow.api.deps import owned_account
from mediaflow.db import get_session
from mediaflow.domain.models import Account, Topic, TopicStatus
from mediaflow.domain.schemas import SourceStatusOut, TopicIn, TopicOut, TopicSearchIn, TopicSearchOut, TopicStatusIn
from mediaflow.llm.client import get_llm
from mediaflow.services.topics import propose_topics

router = APIRouter(prefix="/api/accounts/{account_id}/topics", tags=["topics"])


@router.get("", response_model=list[TopicOut])
def list_topics(status: TopicStatus | None = None, acc: Account = Depends(owned_account),
                s: Session = Depends(get_session)):
    q = select(Topic).where(Topic.account_id == acc.id)
    if status:
        q = q.where(Topic.status == status)
    return [TopicOut(**t.model_dump()) for t in s.exec(q.order_by(col(Topic.created_at).desc()).limit(200)).all()]


@router.post("", response_model=TopicOut, status_code=201)
def add_topic(body: TopicIn, acc: Account = Depends(owned_account), s: Session = Depends(get_session)):
    t = Topic(user_id=acc.user_id, account_id=acc.id, title=body.title.strip(), angle=body.angle, source="user")
    s.add(t)
    s.commit()
    return TopicOut(**t.model_dump())


@router.post("/search", response_model=TopicSearchOut)
async def search_topics(body: TopicSearchIn, acc: Account = Depends(owned_account),
                        s: Session = Depends(get_session)):
    p = await propose_topics(s, get_llm(), load_context(s, acc.id), direction=body.direction, count=5)
    return TopicSearchOut(
        topics=[TopicOut(**t.model_dump()) for t in p.topics],
        sources=[SourceStatusOut(**st.__dict__) for st in p.report.statuses],
        note=p.source_note, skipped_duplicates=p.skipped_duplicates,
    )


@router.patch("/{topic_id}", response_model=TopicOut)
def set_topic_status(topic_id: str, body: TopicStatusIn, acc: Account = Depends(owned_account),
                     s: Session = Depends(get_session)):
    t = s.get(Topic, topic_id)
    if t is None or t.account_id != acc.id:
        raise HTTPException(404, "选题不存在")
    t.status = body.status
    s.add(t)
    s.commit()
    return TopicOut(**t.model_dump())
