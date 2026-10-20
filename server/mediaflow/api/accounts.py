from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlmodel import Session, col, func, select

from mediaflow.api.deps import current_user_id, owned_account
from mediaflow.db import get_session
from mediaflow.domain.models import (
    Account, Benchmark, Draft, DraftStatus, Job, JobKind, JobStatus, Note, Rule, utcnow,
)
from mediaflow.domain.schemas import (
    AccountDetail, AccountIn, AccountOut, AccountPatch, AccountSummary, BenchmarkIn, BenchmarkOut, CandidatesIn,
    JobOut, NoteOut, RemoveBenchmarkOut, RuleIn, RuleOut, VisualLearnIn, VisualPatch,
)
from mediaflow.llm.client import get_llm
from mediaflow.services import bench_report
from mediaflow.services import benchmark as bench

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


def _detail(s: Session, acc: Account) -> AccountDetail:
    rules = s.exec(select(Rule).where(Rule.account_id == acc.id, Rule.active == True)  # noqa: E712
                   .order_by(col(Rule.created_at))).all()
    notes = s.exec(select(Note).where(Note.account_id == acc.id).order_by(col(Note.created_at).desc())).all()
    return AccountDetail(**acc.model_dump(), rules=[RuleOut(**r.model_dump()) for r in rules],
                         notes=[NoteOut(**n.model_dump()) for n in notes],
                         benchmarks=[BenchmarkOut(**b.model_dump()) for b in bench.listing(s, acc.id)])


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
    """加 1-3 个对标账号：后台逐个拆解打法，再和已有的对标合成一套、换成你的主题，同步到账号定位、规则和选题库。"""
    get_llm()  # 没配模型直接报错，不白跑抓取
    job, _ = bench.add(s, acc, [*body.targets, body.target], theme=body.theme, platform=body.platform,
                       names=dict(zip(body.targets, body.names)))
    return JobOut(**job.model_dump())


@router.post("/{account_id}/benchmark/candidates", response_model=JobOut, status_code=202)
def find_candidates(body: CandidatesIn, acc: Account = Depends(owned_account), s: Session = Depends(get_session)):
    """按方向找同领域、有爆款的小红书博主（后台任务，大约半分钟到一分钟）。结果存到账号的 bench_candidates，
    对标页按小红书的样子展示，用户勾选后再调 POST /benchmark。"""
    get_llm()
    return JobOut(**bench.start_find(s, acc, body.query, body.prefer).model_dump())


@router.post("/{account_id}/visual/learn", response_model=JobOut, status_code=202)
def learn_visual(body: VisualLearnIn, acc: Account = Depends(owned_account), s: Session = Depends(get_session)):
    """学账号配图模板（后台任务，大约 1 分钟）：给了笔记链接就照这几篇学，不给就看对标账号的爆款图。要能看图的模型。"""
    from mediaflow.jobs.queue import enqueue
    from mediaflow.llm.client import vision_available
    from mediaflow.services import refpost, visual

    if not vision_available():
        raise HTTPException(400, "现在用的模型看不了图，学不了配图模板（需要配好 DeepSeek Key）")
    links = refpost.split_links(body.links) if body.links.strip() else []
    if body.links.strip() and not links:
        raise HTTPException(400, "没看到小红书笔记链接")
    if not links and not visual._posts_from_benchmarks(s, acc):
        raise HTTPException(400, "还没有学好的对标账号，先加对标，或者给几篇图文笔记链接")
    job = enqueue(s, JobKind.learn_visual, user_id=acc.user_id, account_id=acc.id, payload={"links": links})
    return JobOut(**job.model_dump())


@router.patch("/{account_id}/visual", response_model=AccountDetail)
def update_visual(body: VisualPatch, acc: Account = Depends(owned_account), s: Session = Depends(get_session)):
    """手动改配图模板：改整体视觉、改/删页型（样例图按页型名字沿用）。"""
    from mediaflow.services import visual

    try:
        visual.patch(s, acc, spec=body.spec,
                     pages_in=None if body.pages is None else [p.model_dump(by_alias=True) for p in body.pages])
    except visual.VisualError as e:
        raise HTTPException(400, str(e)) from e
    return _detail(s, acc)


@router.delete("/{account_id}/visual", response_model=AccountDetail)
def clear_visual(acc: Account = Depends(owned_account), s: Session = Depends(get_session)):
    """不用配图模板了：以后配图照每篇的参考帖做。"""
    from mediaflow.services import visual

    visual.patch(s, acc, clear=True)
    return _detail(s, acc)


@router.get("/{account_id}/benchmark/report", response_class=PlainTextResponse,
            responses={200: {"content": {"text/markdown": {}}}})
def benchmark_report(download: bool = False, acc: Account = Depends(owned_account), s: Session = Depends(get_session)):
    """完整的对标报告（Markdown）：合成方案、已经改好的设定、每个对标账号的拆解和爆款。download=true 时作为 .md 下载。"""
    benches = bench.ready(s, acc.id)
    if not benches:
        raise HTTPException(404, "还没有拆好的对标账号")
    headers = {}
    if download:
        name = quote(f"对标报告-{acc.name}.md")
        headers["Content-Disposition"] = f"attachment; filename=\"report.md\"; filename*=UTF-8''{name}"
    return PlainTextResponse(bench_report.markdown(acc, benches), media_type="text/markdown; charset=utf-8", headers=headers)


@router.delete("/{account_id}/benchmark/{benchmark_id}", response_model=RemoveBenchmarkOut)
def remove_benchmark(benchmark_id: str, acc: Account = Depends(owned_account), s: Session = Depends(get_session)):
    """不再对标某个账号：它的复刻选题收起；还有别的对标就自动重新合成方案（返回任务），一个不剩就撤掉对标规则。
    已经同步到账号的定位保留，可以自己改。"""
    b = s.get(Benchmark, benchmark_id)
    if b is None or b.account_id != acc.id:
        raise HTTPException(404, "对标记录不存在")
    job = bench.remove(s, acc, b)
    return RemoveBenchmarkOut(job=JobOut(**job.model_dump()) if job else None)


_ = AccountOut  # 供 OpenAPI 引用
