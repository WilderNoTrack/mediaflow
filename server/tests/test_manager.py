from sqlmodel import select

from mediaflow.agents.manager import TOOLS, chat
from mediaflow.domain.models import Account, ChatRole, Job, Rule, Topic
from tests.fakes import fail, say, tool_call


def test_tools_never_take_account_id():
    for t in TOOLS:
        assert "account_id" not in t["function"]["parameters"]["properties"]


async def test_updates_profile_and_remembers_it(session, llm, account):
    llm.push("manager", tool_call("update_profile", content_style="毒舌但真诚"), say("改好了，文案风格换成毒舌但真诚"))
    msgs = await chat(session, llm, account.id, "以后说话毒舌一点")
    assert [m.role for m in msgs] == [ChatRole.user, ChatRole.tool, ChatRole.assistant]
    session.refresh(account)
    assert account.content_style == "毒舌但真诚"

    # 下一轮：上一轮做过的操作在上下文里
    llm.push("manager", say("刚才把风格改成了毒舌但真诚"))
    await chat(session, llm, account.id, "你刚才改了啥")
    last_messages = llm.calls[-1][1]
    assert any("update_profile" in (m.get("content") or "") for m in last_messages)
    assert "毒舌但真诚" in last_messages[0]["content"]  # 账号快照也是最新的


async def test_rules_add_and_remove(session, llm, account):
    llm.push("manager", tool_call("add_rule", text="每篇结尾引导收藏"), say("记住了"))
    await chat(session, llm, account.id, "以后每篇结尾都引导收藏")
    rule = session.exec(select(Rule).where(Rule.account_id == account.id)).one()
    assert rule.source.value == "chat"

    other = Account(user_id="local", name="别的号")
    session.add(other)
    session.commit()
    foreign = Rule(user_id="local", account_id=other.id, text="别人的规则")
    session.add(foreign)
    session.commit()
    llm.push("manager", tool_call("remove_rule", rule_id=foreign.id), say("删不了"))
    msgs = await chat(session, llm, account.id, "删掉那条")
    assert msgs[1].payload["result"]["ok"] is False
    session.refresh(foreign)
    assert foreign.active


async def test_write_post_enqueues_background_job(session, llm, account):
    llm.push("manager", tool_call("write_post", hint="秋季"), say("开始写了"))
    msgs = await chat(session, llm, account.id, "写一篇秋季的")
    job = session.exec(select(Job)).one()
    assert job.account_id == account.id and job.payload["trigger"] == "chat"
    assert msgs[1].payload["result"]["job_id"] == job.id


async def test_find_topics_reports_failed_sources(session, llm, account):
    llm.push("manager", tool_call("find_topics"), say("找到啦"))
    msgs = await chat(session, llm, account.id, "找几个选题")
    result = msgs[1].payload["result"]
    assert result["ok"] and result["topics"] and "B站" in result["source_note"]
    assert session.exec(select(Topic)).all()


async def test_llm_failure_keeps_user_message(session, llm, account):
    llm.push("manager", fail("timeout"))
    msgs = await chat(session, llm, account.id, "在吗")
    assert msgs[0].content == "在吗" and "连不上" in msgs[-1].content


async def test_bad_tool_arguments_are_reported_back(session, llm, account):
    from mediaflow.llm.client import LLMResponse, ToolCall
    bad = LLMResponse(tool_calls=[ToolCall(id="c1", name="add_rule", arguments={}, error="参数不是合法 JSON")])
    llm.push("manager", bad, tool_call("add_rule", text="不用感叹号"), say("记住了"))
    msgs = await chat(session, llm, account.id, "以后别用感叹号")
    assert "合法 JSON" in msgs[1].content and msgs[-1].content == "记住了"
    assert session.exec(select(Rule).where(Rule.account_id == account.id)).one().text == "不用感叹号"


async def test_step_limit_ends_with_summary_not_canned_text(session, llm, account):
    from mediaflow.agents.manager import MAX_STEPS
    llm.push("manager", *[tool_call("list_drafts") for _ in range(MAX_STEPS)], say("我查了几遍草稿，目前还没有"))
    msgs = await chat(session, llm, account.id, "看看草稿")
    assert msgs[-1].content == "我查了几遍草稿，目前还没有"
    assert "tools" not in str(llm.calls[-1][1][-1]) and "上限" in llm.calls[-1][1][-1]["content"]


async def test_research_tools_run_in_parallel_and_save_note(session, llm, account, monkeypatch):
    import asyncio
    import json

    from mediaflow.agents.context import load_context
    from mediaflow.domain.models import Note
    from mediaflow.llm.client import LLMResponse, ToolCall
    from mediaflow.research import service

    running, peak = 0, 0

    async def slow(result):
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.05)
        running -= 1
        return result

    async def creators(platform, name, limit=5):
        return await slow({"platform": platform, "creators": [{"ref": "xhs:c1", "name": name, "fans": "776.9万"}]})

    async def posts(ref, limit=10, sort="latest"):
        return await slow({"platform": "xiaohongshu", "creator": {"ref": ref}, "posts": [{"ref": "xhs:p2", "title": "爆款" * 2500}]})

    monkeypatch.setattr(service, "search_creators", creators)
    monkeypatch.setattr(service, "creator_posts", posts)
    both = LLMResponse(tool_calls=[ToolCall(id="a", name="research_creators", arguments={"platform": "xiaohongshu", "name": "程十安"}),
                                   ToolCall(id="b", name="research_creator_posts", arguments={"creator_ref": "xhs:c1", "sort": "top"})])
    llm.push("manager", both, tool_call("save_note", title="对标：程十安", content="标题爱用数字；封面大字"), say("分析好了，已存成笔记"))
    msgs = await chat(session, llm, account.id, "帮我分析一下程十安")

    assert peak == 2  # 两个只读调研同时跑
    assert [m.tool_name for m in msgs if m.role == ChatRole.tool] == ["research_creators", "research_creator_posts", "save_note"]
    assert json.loads(msgs[1].content)["creators"][0]["fans"] == "776.9万"
    assert len(msgs[2].content) < 4100 and msgs[2].content.endswith("已截断）")  # 长结果截断，完整结果在 payload
    note = session.exec(select(Note).where(Note.account_id == account.id)).one()
    assert "标题爱用数字" in load_context(session, account.id).profile_text()

    # 下一轮：笔记在账号状态里，历史里的调研结果只留摘要
    llm.push("manager", say("好"))
    await chat(session, llm, account.id, "嗯")
    ctx = llm.calls[-1][1]
    assert note.id in ctx[0]["content"]
    hist = [m["content"] for m in ctx[1:] if "我执行了 research_creator_posts" in (m.get("content") or "")]
    assert hist and len(hist[0]) < 600


async def test_research_errors_are_reported(session, llm, account, monkeypatch):
    from mediaflow.sources import platforms
    monkeypatch.setattr(platforms.credentials, "get", lambda k: "")
    from mediaflow.llm.client import LLMResponse, ToolCall
    llm.push("manager", LLMResponse(tool_calls=[ToolCall(id="a", name="research_creators",
                                                         arguments={"platform": "xiaohongshu", "name": "x"})]),
             tool_call("research_post", post_ref="xhs:p99999"), say("小红书没登录"))
    msgs = await chat(session, llm, account.id, "查下x")
    assert "没登录" in msgs[1].payload["result"]["error"] and "重新搜索" in msgs[2].payload["result"]["error"]


async def test_research_search_keeps_refs_and_notes(session, llm, account, monkeypatch):
    from mediaflow.sources import registry
    from mediaflow.sources.base import SourceReport, SourceStatus, TrendItem

    async def fake(keyword, limit=8, sources=None):
        return SourceReport(items=[TrendItem(title="早八妆", source="xiaohongshu", heat="1万赞", ref="n1|tk",
                                             url="https://www.xiaohongshu.com/explore/n1")],
                            statuses=[SourceStatus(source="douyin", label="抖音", ok=False, note="抓取失败（超时）")])
    monkeypatch.setattr(registry, "fetch_all", fake)
    llm.push("manager", tool_call("research_search", keyword="早八妆"), say("搜到了"))
    msgs = await chat(session, llm, account.id, "搜下早八妆")
    r = msgs[1].payload["result"]
    assert r["items"][0]["ref"].startswith("xhs:p") and r["source_notes"] == ["抖音：抓取失败（超时）"]


async def test_notes_are_scoped_to_account(session, llm, account):
    from mediaflow.domain.models import Note
    other = Account(user_id="local", name="别的号")
    session.add(other)
    session.commit()
    n = Note(user_id="local", account_id=other.id, title="别人的", content="x")
    session.add(n)
    session.commit()
    llm.push("manager", tool_call("remove_note", note_id=n.id), say("删不了"))
    msgs = await chat(session, llm, account.id, "删掉那条笔记")
    assert msgs[1].payload["result"]["ok"] is False and session.get(Note, n.id) is not None
