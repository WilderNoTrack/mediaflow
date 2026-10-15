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
