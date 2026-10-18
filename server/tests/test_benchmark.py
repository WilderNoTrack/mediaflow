"""复刻对标账号：拆解 → 换主题出方案 → 同步账号 → 写稿用复刻选题并参考原爆款。"""

import pytest
from sqlmodel import select

from mediaflow.agents.context import load_context
from mediaflow.agents.pipeline import write_draft
from mediaflow.domain.models import Benchmark, BenchmarkStatus, Rule, RuleSource, Topic, TopicStatus
from mediaflow.research import service as research
from mediaflow.research.types import Creator, Post, PostDetail
from mediaflow.services import benchmark as bench
from mediaflow.sources import xhs
from tests.fakes import evaluation, post

PLAYBOOK = {"summary": "干货教程×真人出镜×闺蜜口吻", "persona": "懂行的闺蜜",
            "pillars": [{"name": "底妆教程", "share": "约5成", "desc": "手把手", "examples": ["裸感底妆"]}],
            "title_formulas": [{"formula": "干货｜结果+效果词", "example": "干货 | 真正裸感底妆的打造"}],
            "hooks": ["又是一个很长但很干的视频"], "structure": "1.痛点 2.步骤 3.总结", "visual": "大字封面",
            "not_copyable": ["颜值"]}
PLAN = {"profile": {"theme": "模型改写的主题", "audience": "刚工作的年轻人", "content_style": "懂行闺蜜口吻",
                    "image_style": "大字封面+步骤图", "topic_type": "理财教程", "keywords": ["存钱", "基金"]},
        "rules": ["标题用「干货｜结果」公式", "开头先说痛点"],
        "pillars": [{"name": "存钱教程", "from": "底妆教程", "share": "约5成"}],
        "topics": [{"title": "干货｜月薪5千的存钱底层逻辑", "angle": "手把手", "ref": 1, "why": "套干货公式"},
                   {"title": "工资到账后先做这3件事", "angle": "清单", "ref": 2, "why": "复刻清单体"},
                   {"title": "干货｜真正裸感底妆的打造", "angle": "照抄", "ref": 1, "why": "原样照抄要被丢掉"}],
        "steps": ["前两周每天一篇教程"]}


@pytest.fixture
def fake_research(monkeypatch):
    calls = []

    async def resolve(platform, target):
        calls.append(("resolve", target))
        return Creator(platform=platform, name="程十安an", native="u1|tk", fans="776万")

    async def posts(platform, native, n=60):
        return (Creator(platform=platform, name="程十安an", native=native, fans="776万", desc="美妆",
                        url="https://www.xiaohongshu.com/user/profile/u1"),
                [Post(platform=platform, title="普通日常", native="n0|t", likes="800", published="2023-05-01", kind="图文"),
                 Post(platform=platform, title="干货 | 真正裸感底妆的打造", native="n1|t", likes="10万+",
                      published="2023-05-04", kind="视频", url="https://x/n1"),
                 Post(platform=platform, title="顽固闭口实战贴", native="n2|t", likes="5.2万", published="2023-04-14",
                      kind="视频")])

    async def detail(platform, native):
        if native == "n2|t":
            raise RuntimeError("风控")
        return PostDetail(platform=platform, title="干货 | 真正裸感底妆的打造" if native == "n1|t" else "普通日常",
                          native=native, likes="10万+", content="又是一个很长但很干的视频", tags=["底妆"],
                          top_comments=["672赞｜T区用清爽精华水"], url="https://x/n1")

    monkeypatch.setattr(research, "resolve_creator", resolve)
    monkeypatch.setattr(research, "creator_posts_raw", posts)
    monkeypatch.setattr(research, "post_detail_raw", detail)
    return calls


async def test_clone_flow(session, account, llm, fake_research):
    old = Rule(user_id=account.user_id, account_id=account.id, text="旧对标规则", source=RuleSource.benchmark)
    session.add(old)
    b = Benchmark(user_id=account.user_id, account_id=account.id, target="程十安", theme="职场新人理财")
    session.add(b)
    session.commit()
    llm.push("bench_analyze", PLAYBOOK).push("bench_adapt", PLAN)
    events = []
    await bench.analyze(session, llm, b.id, emit=lambda st, m, d=None: events.append((st, m)))

    session.refresh(b)
    assert b.status == BenchmarkStatus.ready and b.creator_name == "程十安an"
    assert b.creator_info["fans"] == "776万" and b.creator_info["posts_read"] == 3
    assert b.samples[0]["title"].startswith("干货") and b.samples[0]["content"]  # 按点赞排序，带详情
    assert "content" not in b.samples[1]  # 详情失败的只留列表数据
    assert any(st == "warning" for st, _ in events) and events[-1][0] == "done"
    analyze_prompt = llm.prompts_of("bench_analyze")[0]
    assert "external_data" in analyze_prompt and "10万+" in analyze_prompt

    session.refresh(account)
    assert account.theme == "职场新人理财"  # 用户说的主题优先
    assert account.image_style == "大字封面+步骤图" and account.keywords == ["存钱", "基金"]
    rules = session.exec(select(Rule).where(Rule.account_id == account.id, Rule.active == True)).all()  # noqa: E712
    assert {r.text for r in rules} >= {"标题用「干货｜结果」公式"} and "旧对标规则" not in {r.text for r in rules}
    topics = session.exec(select(Topic).where(Topic.source == "benchmark")).all()
    assert len(topics) == 2 and topics[0].reference["title"].startswith("干货")
    assert account.bench_plan["applied"]["topics"] and account.bench_plan["steps"]
    assert account.bench_plan["creators"] == ["程十安an"]

    # 上下文带上打法；写稿默认用复刻选题，并把原爆款作为结构参考
    ctx = load_context(session, account.id)
    assert "对标账号打法" in ctx.profile_text() and "干货｜结果+效果词" in ctx.profile_text()
    llm.push("writer", post()).push("eval", evaluation(8.5))
    d = await write_draft(session, llm, account.id)
    t = session.get(Topic, d.topic_id)
    assert t.source == "benchmark" and t.status == TopicStatus.used
    w = llm.prompts_of("writer")[0]
    assert "参考爆款" in w and "又是一个很长但很干的视频" in w and "不照抄" in w


async def test_clone_failure_marks_benchmark(session, account, llm, monkeypatch):
    async def resolve(platform, target):
        raise LookupError("没搜到「谁」")

    monkeypatch.setattr(research, "resolve_creator", resolve)
    b = Benchmark(user_id=account.user_id, account_id=account.id, target="谁")
    session.add(b)
    session.commit()
    with pytest.raises(RuntimeError, match="没搜到"):
        await bench.analyze(session, llm, b.id)
    session.refresh(b)
    assert b.status == BenchmarkStatus.failed and "没搜到" in b.error


async def test_resolve_link():
    assert await xhs.resolve_link("看这个 https://www.xiaohongshu.com/user/profile/562ef75ae00dd861d410784a?xsec_token=AB1&xsec_source=pc") \
        == ("creator", "562ef75ae00dd861d410784a|AB1")
    assert await xhs.resolve_link("https://www.xiaohongshu.com/explore/64537ba5000000001300fd56?xsec_token=T") \
        == ("post", "64537ba5000000001300fd56|T")
    assert await xhs.resolve_link("程十安an") == ("", "")


async def test_resolve_creator_by_name(monkeypatch):
    async def search(name, limit):
        return [Creator("xiaohongshu", "程十安ann", "a|", fans="4"), Creator("xiaohongshu", "程十安an", "b|", fans="776万"),
                Creator("xiaohongshu", "程十安an", "c|", fans="12")]

    monkeypatch.setattr(xhs, "search_creators", search)
    monkeypatch.setattr(research, "_MIN_GAP", 0)
    research._cache.clear()
    assert (await research.resolve_creator("xiaohongshu", "程十安an")).native == "b|"


def test_api_clone(client, account, monkeypatch, llm):
    r = client.post(f"/api/accounts/{account.id}/benchmark", json={"targets": ["程十安", "小雨攒钱笔记"], "theme": "职场理财"})
    assert r.status_code == 201 and r.json()["kind"] == "clone_creator" and len(r.json()["payload"]["benchmark_ids"]) == 2
    r2 = client.post(f"/api/accounts/{account.id}/benchmark", json={"target": "程十安"})
    assert r2.status_code == 409
    detail = client.get(f"/api/accounts/{account.id}").json()
    assert [b["status"] for b in detail["benchmarks"]] == ["analyzing", "analyzing"]
    bid = detail["benchmarks"][0]["id"]
    from mediaflow.domain.models import Job, JobStatus
    from sqlmodel import Session
    from mediaflow.db import get_engine
    with Session(get_engine()) as s:  # 让任务结束，才能删
        for j in s.exec(select(Job)).all():
            j.status = JobStatus.failed
            s.add(j)
        s.commit()
    r3 = client.delete(f"/api/accounts/{account.id}/benchmark/{bid}")
    assert r3.status_code == 200 and r3.json()["job"] is None  # 没拆完的删了不用重新合成
    assert len(client.get(f"/api/accounts/{account.id}").json()["benchmarks"]) == 1


async def test_manager_clone_tool(session, account, llm):
    from mediaflow.agents.manager import Toolbox
    from mediaflow.domain.models import Job, JobKind

    tb = Toolbox(session, llm, account, None)
    r = await tb.call("clone_creator", {"targets": ["https://www.xiaohongshu.com/user/profile/abc"], "theme": "职场理财"})
    assert r["ok"]
    job = session.get(Job, r["job_id"])
    assert job.kind == JobKind.clone_creator and session.get(Benchmark, job.payload["benchmark_ids"][0]).theme == "职场理财"
    again = await tb.call("clone_creator", {"targets": ["x"]})
    assert not again["ok"] and "正在拆解" in again["error"]
    assert tb.snapshot()["benchmarks"][0]["status"] == "analyzing"


UID_A, UID_B, UID_C = "a" * 24, "b" * 24, "c" * 24


@pytest.fixture
def multi_research(monkeypatch):
    names = {UID_A: "穿搭阿A", UID_B: "通勤小B", UID_C: "美妆C"}

    async def resolve(platform, target):
        uid = next(u for u, n in names.items() if n == target)
        return Creator(platform=platform, name=names[uid], native=f"{uid}|t")

    async def posts(platform, native, n=60):
        uid = native.split("|")[0]
        return (Creator(platform=platform, name=names[uid], native=native, fans="10万",
                        url=f"https://www.xiaohongshu.com/user/profile/{uid}"),
                [Post(platform=platform, title=f"{names[uid]}的爆款{i}", native=f"{uid}{i}|t", likes=str(1000 * (5 - i)),
                      published=f"2024-05-0{i + 1}", kind="图文") for i in range(4)])

    async def detail(platform, native):
        raise RuntimeError("风控")

    monkeypatch.setattr(research, "resolve_creator", resolve)
    monkeypatch.setattr(research, "creator_posts_raw", posts)
    monkeypatch.setattr(research, "post_detail_raw", detail)
    return names


async def test_multi_benchmark_merge(session, account, llm, multi_research):
    from mediaflow.domain.models import Job

    job, new = bench.add(session, account, ["穿搭阿A", "通勤小B"], theme="通勤穿搭")
    assert len(new) == 2 and job.payload["benchmark_ids"] == [b.id for b in new]
    plan = {**PLAN, "summary": "栏目学A，标题学B", "borrow": [{"aspect": "标题", "from": "通勤小B", "how": "数字+场景"}],
            "topics": [{"title": "一周通勤不重样", "ref": "A1", "why": "学A"}, {"title": "小个子通勤3件套", "ref": "B2", "why": "学B"},
                       {"title": "穿搭阿A的爆款0", "ref": "A1", "why": "照抄要丢"}]}
    llm.push("bench_analyze", PLAYBOOK, PLAYBOOK).push("bench_adapt", plan)
    out = await bench.run(session, llm, account.id, job.payload["benchmark_ids"], "通勤穿搭")
    assert out["creators"] == ["穿搭阿A", "通勤小B"] and out["topics"] == 2
    adapt = llm.prompts_of("bench_adapt")[0]
    assert "A1｜穿搭阿A的爆款0" in adapt and "B2｜通勤小B的爆款1" in adapt
    topics = session.exec(select(Topic).where(Topic.source == "benchmark", Topic.status == TopicStatus.new)).all()
    assert {t.reference["creator"] for t in topics} == {"穿搭阿A", "通勤小B"}
    session.refresh(account)
    assert account.bench_plan["summary"] == "栏目学A，标题学B" and account.theme == "通勤穿搭"
    text = load_context(session, account.id).profile_text()
    assert "合成打法：栏目学A，标题学B" in text and "穿搭阿A" in text and "通勤小B" in text

    # 上限 3 个；重复的跳过
    session.exec(select(Job)).first().status = "succeeded"
    session.commit()
    with pytest.raises(ValueError, match="已经在对标"):
        bench.add(session, account, ["穿搭阿A"])
    with pytest.raises(ValueError, match="最多同时对标 3 个"):
        bench.add(session, account, ["美妆C", "x", "y"])

    # 删一个：它的选题收起，剩下的重新合成；全删：对标规则和方案撤掉
    a, b = new
    for j in session.exec(select(Job)).all():
        j.status = "succeeded"
    session.commit()
    job2 = bench.remove(session, account, a)
    assert job2 is not None and job2.payload["benchmark_ids"] == []
    left = session.exec(select(Topic).where(Topic.source == "benchmark", Topic.status == TopicStatus.new)).all()
    assert {t.reference["creator"] for t in left} == {"通勤小B"}
    job2.status = "succeeded"
    session.commit()
    assert bench.remove(session, account, b) is None
    session.refresh(account)
    assert account.bench_plan == {}
    assert not session.exec(select(Rule).where(Rule.source == RuleSource.benchmark, Rule.active == True)).all()  # noqa: E712


async def test_multi_benchmark_one_fails(session, account, llm, multi_research):
    job, new = bench.add(session, account, ["穿搭阿A", "不存在"], theme="通勤穿搭")
    llm.push("bench_analyze", PLAYBOOK).push("bench_adapt", PLAN)
    events = []
    out = await bench.run(session, llm, account.id, job.payload["benchmark_ids"], "通勤穿搭",
                          emit=lambda st, m, d=None: events.append((st, m)))
    assert out["creators"] == ["穿搭阿A"]
    session.refresh(new[1])
    assert new[1].status == BenchmarkStatus.failed
    assert any(st == "warning" and "没拆成" in m for st, m in events)


async def test_find_candidates(session, account, llm, monkeypatch, multi_research):
    async def hot(platform, kw):
        return [{"user_id": UID_A, "name": "穿搭阿A", "avatar": "http://a", "native": f"{UID_A}|t", "title": "通勤穿搭公式", "likes": "2万", "url": "u1"},
                {"user_id": UID_B, "name": "通勤小B", "avatar": "", "native": f"{UID_B}|t", "title": "小个子通勤", "likes": "5000", "url": "u2"},
                {"user_id": UID_C, "name": "美妆C", "avatar": "", "native": f"{UID_C}|t", "title": "偶尔一篇穿搭", "likes": "9万", "url": "u3"},
                {"user_id": UID_A, "name": "穿搭阿A", "avatar": "", "native": f"{UID_A}|t", "title": "通勤一周", "likes": "1万", "url": "u4"}]

    async def creators(platform, kw, n=10):
        return [Creator(platform, "美妆C", f"{UID_C}|t", fans="50万"), Creator(platform, "小号", "d" * 24 + "|t", fans="300")]

    monkeypatch.setattr(research, "hot_authors_raw", hot)
    monkeypatch.setattr(research, "creators_raw", creators)
    llm.push("bench_pick", {"picks": [{"no": 1, "fit": 9, "level": "腰部", "reason": "通勤公式化标题"},
                                      {"no": 2, "fit": 2, "reason": "主要做美妆"}]})
    out = await bench.find_candidates(llm, "通勤穿搭", exclude=["通勤小B"])
    names = [c["name"] for c in out["candidates"]]
    assert names == ["穿搭阿A"]  # 通勤小B 已在对标被排除；美妆C 不同领域被筛掉
    c = out["candidates"][0]
    assert c["reason"] == "通勤公式化标题" and len(c["hits"]) == 2 and c["median_likes"] and UID_A in c["url"]
    assert any("不做这个方向" in n for n in out["notes"])
    pick_prompt = llm.prompts_of("bench_pick")[0]
    assert "穿搭阿A" in pick_prompt and "通勤小B" not in pick_prompt

    from mediaflow.agents.manager import _for_model
    brief = _for_model("find_benchmarks", {"ok": True, **out})
    assert "avatar" not in brief["candidates"][0] and brief["candidates"][0]["no"] == 1
