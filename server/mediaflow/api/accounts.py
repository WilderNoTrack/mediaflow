from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, col, func, select

from mediaflow.api.deps import current_user_id, owned_account
from mediaflow.db import get_session
from mediaflow.domain.models import (
    Account, Benchmark, Draft, DraftStatus, Job, JobKind, JobStatus, Note, Rule, Topic, TopicStatus, utcnow,
)
from mediaflow.domain.schemas import (
    AccountDetail, AccountIn, AccountOut, AccountPatch, AccountSummary, BenchmarkIn, BenchmarkOut, JobOut, NoteOut,
    RuleIn, RuleOut,
)
from mediaflow.jobs.queue import JobConflict, active_write_job, enqueue
from mediaflow.llm.client import get_llm
from mediaflow.services import benchmark as bench

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


def _detail(s: Session, acc: Account) -> AccountDetail:
    rules = s.exec(select(Rule).where(Rule.account_id == acc.id, Rule.active == True)  # noqa: E712
                   .order_by(col(Rule.created_at))).all()
    notes = s.exec(select(Note).where(Note.account_id == acc.id).order_by(col(Note.created_at).desc())).all()
    b = bench.latest(s, acc.id)
    return AccountDetail(**acc.model_dump(), rules=[RuleOut(**r.model_dump()) for r in rules],
                         notes=[NoteOut(**n.model_dump()) for n in notes],
                         benchmark=BenchmarkOut(**b.model_dump()) if b else None)


@router.get("", response_model=list[AccountSummary])
def list_accounts(s: Session = Depends(get_session), uid: str = Depends(current_user_id)):
    accs = s.exec(select(Account).where(Account.user_id == uid).order_by(col(Account.created_at))).all()
    out = []
    for a in accs:
        pending = s.exec(select(func.count()).select_from(Draft).where(
            Draft.account_id == a.id, Draft.status == DraftStatus.pending_review)).one()
        total = s.exec(select(func.count()).select_from(Draft).where(Draft.account_id == a.id)).one()
        writing = s.exec(select(Job.id).where(
            Job.account_id == a.id, Job.kind == JobKind.write_draft,
            col(Job.status).in_([JobStatus.queued, JobStatus.running]))).first() is not None
        out.append(AccountSummary(**a.model_dump(), pending_review=pending, total_drafts=total, writing=writing))
    return out


@router.post("", response_model=AccountDetail, status_code=201)
def create_account(body: AccountIn, s: Session = Depends(get_session), uid: str = Depends(current_user_id)):
    acc = Account(user_id=uid, **body.model_dump())
    s.add(acc)
    s.commit()
    return _detail(s, acc)


@router.get("/{account_id}", response_model=AccountDetail)
def get_account(acc: Account = Depends(owned_account), s: Session = Depends(get_session)):
    return _detail(s, acc)


@router.patch("/{account_id}", response_model=AccountDetail)
def update_account(body: AccountPatch, acc: Account = Depends(owned_account), s: Session = Depends(get_session)):
    for k, v in body.model_dump(exclude_unset=True).items():
        if v is not None:
            setattr(acc, k, v)
    acc.updated_at = utcnow()
    s.add(acc)
    s.commit()
    return _detail(s, acc)


@router.delete("/{account_id}", status_code=204)
def delete_account(acc: Account = Depends(owned_account), s: Session = Depends(get_session)):
    from mediaflow.domain.models import ChatMessage, DraftImage, Feedback, Topic

    draft_ids = s.exec(select(Draft.id).where(Draft.account_id == acc.id)).all()
    for model, cond in (
        (DraftImage, col(DraftImage.draft_id).in_(draft_ids)),
        (Feedback, col(Feedback.draft_id).in_(draft_ids)),
        (Draft, Draft.account_id == acc.id),
        (Topic, Topic.account_id == acc.id),
        (Rule, Rule.account_id == acc.id),
        (Note, Note.account_id == acc.id),
        (Benchmark, Benchmark.account_id == acc.id),
        (ChatMessage, ChatMessage.account_id == acc.id),
        (Job, Job.account_id == acc.id),
    ):
        for row in s.exec(select(model).where(cond)).all():
            s.delete(row)
        s.flush()
    s.delete(acc)
    s.commit()


@router.post("/{account_id}/rules", response_model=RuleOut, status_code=201)
def add_rule(body: RuleIn, acc: Account = Depends(owned_account), s: Session = Depends(get_session)):
    r = Rule(user_id=acc.user_id, account_id=acc.id, text=body.text.strip(), source=body.source)
    s.add(r)
    s.commit()
    return RuleOut(**r.model_dump())


@router.delete("/{account_id}/rules/{rule_id}", status_code=204)
def remove_rule(rule_id: str, acc: Account = Depends(owned_account), s: Session = Depends(get_session)):
    r = s.get(Rule, rule_id)
    if r is None or r.account_id != acc.id:
        raise HTTPException(404, "规则不存在")
    r.active = False
    s.add(r)
    s.commit()



@router.delete("/{account_id}/notes/{note_id}", status_code=204)
def remove_note(note_id: str, acc: Account = Depends(owned_account), s: Session = Depends(get_session)):
    n = s.get(Note, note_id)
    if n is None or n.account_id != acc.id:
        raise HTTPException(404, "笔记不存在")
    s.delete(n)
    s.commit()


@router.post("/{account_id}/benchmark", response_model=JobOut, status_code=201)
def clone_benchmark(body: BenchmarkIn, acc: Account = Depends(owned_account), s: Session = Depends(get_session)):
    """复刻一个对标账号：后台拆解打法、按新主题出方案，完成后同步到账号定位、规则和选题库。"""
    get_llm()  # 没配模型直接报错，不白跑抓取
    if not (body.theme.strip() or acc.theme):
        raise ValueError("先说一下你想做什么主题，比如「职场新人理财」")
    existing = active_write_job(s, acc.id, JobKind.clone_creator)
    if existing:
        raise JobConflict(existing)
    b = Benchmark(user_id=acc.user_id, account_id=acc.id, platform=body.platform, target=body.target.strip(),
                  theme=body.theme.strip())
    s.add(b)
    s.commit()
    job = enqueue(s, JobKind.clone_creator, user_id=acc.user_id, account_id=acc.id, payload={"benchmark_id": b.id})
    return JobOut(**job.model_dump())


@router.delete("/{account_id}/benchmark/{benchmark_id}", status_code=204)
def remove_benchmark(benchmark_id: str, acc: Account = Depends(owned_account), s: Session = Depends(get_session)):
    """不再对标：删掉拆解记录，没用过的复刻选题收起；已经同步到账号的定位和规则保留，可以自己改。"""
    b = s.get(Benchmark, benchmark_id)
    if b is None or b.account_id != acc.id:
        raise HTTPException(404, "对标记录不存在")
    for t in s.exec(select(Topic).where(Topic.account_id == acc.id, Topic.source == "benchmark",
                                        Topic.status == TopicStatus.new)).all():
        if (t.reference or {}).get("benchmark_id") == b.id:
            t.status = TopicStatus.dismissed
            s.add(t)
    s.delete(b)
    s.commit()


_ = AccountOut  # 供 OpenAPI 引用
