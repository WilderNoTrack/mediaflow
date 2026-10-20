import json

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
    # 历史里是原生的 tool_calls + tool 结果，不是「（我执行了…）」文字（否则模型会学着只写不调）
    calls = [(m, c) for m in last_messages if m["role"] == "assistant" for c in m.get("tool_calls") or []]
    assert [c["function"]["name"] for _, c in calls] == ["update_profile"]
    assert json.loads(calls[0][1]["function"]["arguments"]) == {"content_style": "毒舌但真诚"}
    i = last_messages.index(calls[0][0])
    assert last_messages[i + 1]["role"] == "tool" and last_messages[i + 1]["tool_call_id"] == calls[0][1]["id"]
    assert not any("我执行了" in (m.get("content") or "") for m in last_messages[1:])
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
    ids = {c["id"] for m in ctx[1:] for c in m.get("tool_calls") or [] if c["function"]["name"] == "research_creator_posts"}
    hist = [m["content"] for m in ctx[1:] if m["role"] == "tool" and m["tool_call_id"] in ids]
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


async def test_ask_user_ends_turn_with_buttons(session, llm, account):
    """有常见答案的问题给按钮：同一步的操作照做，问题当回复，选项存进消息；下一轮模型知道用户在回答它。"""
    from mediaflow.llm.client import LLMResponse, ToolCall

    llm.push("manager", LLMResponse(content="记下了～", tool_calls=[
        ToolCall(id="a", name="update_profile", arguments={"theme": "宝妈省钱"}),
        ToolCall(id="b", name="ask_user", arguments={"question": "你的内容主要给谁看？", "multi": True,
                                                      "options": ["新手宝妈", "二胎家庭", "上班族妈妈", "新手宝妈"]})]))
    msgs = await chat(session, llm, account.id, "我想分享带娃省钱")
    assert len(llm.calls) == 1  # 问完这一轮就结束，等用户
    assert [m.role for m in msgs] == [ChatRole.user, ChatRole.tool, ChatRole.assistant]
    session.refresh(account)
    assert account.theme == "宝妈省钱"
    reply = msgs[-1]
    assert reply.content == "记下了～\n\n你的内容主要给谁看？"
    assert reply.payload["ask"] == {"question": "你的内容主要给谁看？", "options": ["新手宝妈", "二胎家庭", "上班族妈妈"],
                                    "multi": True, "kind": "choice"}

    llm.push("manager", tool_call("update_profile", audience="新手宝妈、二胎家庭"), say("好，记下了"))
    await chat(session, llm, account.id, "新手宝妈、二胎家庭")
    ctx = llm.calls[1][1]
    asked = [m for m in ctx if m["role"] == "assistant" and any(c["function"]["name"] == "ask_user" for c in m.get("tool_calls") or [])]
    assert asked and ctx[ctx.index(asked[0]) + 1]["role"] == "tool"
    session.refresh(account)
    assert account.audience == "新手宝妈、二胎家庭"


async def test_fake_tool_call_in_text_is_corrected(session, llm, account):
    """模型在文字里写「（我执行了 update_profile：…）」却没调用：提醒一次让它真调，用户看不到那段假的。"""
    llm.push("manager", say('（我执行了 update_profile：{"audience": "新手宝妈"}）\n\n记下了'),
             tool_call("update_profile", audience="新手宝妈"), say("记下了，受众是新手宝妈"))
    msgs = await chat(session, llm, account.id, "给新手宝妈看的")
    session.refresh(account)
    assert account.audience == "新手宝妈"
    assert msgs[-1].content == "记下了，受众是新手宝妈"
    assert any("没有真正调用工具" in (m.get("content") or "") and m["role"] == "user" for m in llm.calls[-1][1])


def test_sanitize_drops_fake_tool_lines():
    from mediaflow.agents.manager import _sanitize

    assert _sanitize('好的\n\n（我执行了 add_rule：{"text": "x"}）\n\n还有别的吗') == "好的\n\n还有别的吗"
    assert _sanitize("（我执行了 update_profile：{}）") == ""


async def test_second_write_while_running_is_not_a_failure(session, llm, account):
    from mediaflow.agents.manager import Toolbox

    tb = Toolbox(session, llm, account, None)
    first = await tb.call("write_post", {"hint": "省钱"})
    again = await tb.call("write_post", {"hint": "再来一篇"})
    assert first["ok"] and again["ok"] and again["already_running"] and again["job_id"] == first["job_id"]
    assert len(session.exec(select(Job)).all()) == 1


async def test_update_visual_without_template_creates_one(session, llm, account):
    """没对标、没模板时说「配图要清新手绘风」：按描述起一套模板（没有样例图），不再报「先学一个」。"""
    from mediaflow.agents.manager import Toolbox

    account.visual = {}
    session.add(account)
    session.commit()
    llm.push("visual_update", {"spec": "奶油白底、手绘涂鸦、马卡龙色", "changed": "",
                               "pages": [{"type": "清单页", "desc": "序号+要点"}, {"type": "封面", "desc": "大字标题"}]})
    r = await Toolbox(session, llm, account, None).call("update_visual", {"instruction": "清新手绘风"})
    assert r["ok"] and r["created"] and r["pages"] == ["封面", "清单页"]
    session.refresh(account)
    assert account.visual["source"]["names"] == ["按你的描述"] and account.visual["pages"][0]["examples"] == []
    assert "还没有配图模板" in llm.prompts_of("visual_update")[0]


def _turns(session, account, n, start=0, tools=0):
    from mediaflow.agents.manager import _save

    for i in range(start, start + n):
        _save(session, account, ChatRole.user, f"第{i}句：我说过的事情{i}")
        for k in range(tools):
            _save(session, account, ChatRole.tool, "{}", "research_search",
                  {"args": {"keyword": f"词{i}-{k}"}, "result": {"ok": True, "items": ["x" * 3000]}})
        _save(session, account, ChatRole.assistant, f"好的，记下第{i}件事")


async def test_history_counts_turns_not_rows(session, llm, account):
    """调研一轮能产生十几条工具记录：历史按「用户说了几轮」截，不按条数截，不然没几轮就忘了。"""
    _turns(session, account, 12, tools=6)
    llm.push("manager", say("记得"))
    await chat(session, llm, account.id, "还记得我第一句说了啥吗")
    sent = llm.calls[-1][1]
    texts = [m.get("content") or "" for m in sent]
    assert any("第0句" in t for t in texts) and any("第11句" in t for t in texts)
    tool_msgs = [m for m in sent if m["role"] == "tool"]
    assert tool_msgs and all(len(m["content"]) <= 900 for m in tool_msgs)  # 工具结果只留摘要
    first = next(i for i, m in enumerate(sent) if m["role"] != "system")
    assert sent[first]["role"] == "user"  # 窗口从一轮的开头开始


async def test_history_keeps_candidate_links_and_job_outcomes(session, llm, account):
    """「选第 3 个」「刚才那篇」要指得上：找对标的候选链接、写稿任务后来写成了哪篇，都留在历史里。"""
    from mediaflow.agents.manager import _save
    from mediaflow.domain.models import Draft, JobKind, JobStatus

    cands = [{"name": f"博主{i}", "url": f"https://www.xiaohongshu.com/user/profile/u{i}", "avatar": "a" * 300,
              "reason": "很长的理由" * 80, "fans": 1000 * i} for i in range(1, 7)]
    _save(session, account, ChatRole.user, "帮我找几个对标")
    _save(session, account, ChatRole.tool, "{}", "find_benchmarks", {"args": {}, "result": {"ok": True, "candidates": cands}})
    _save(session, account, ChatRole.assistant, "找到 6 个")
    d = Draft(user_id="local", account_id=account.id, title="通勤包里的5件小物", body="b", original_title="t",
              original_body="b", score=8.2)
    job = Job(user_id="local", account_id=account.id, kind=JobKind.write_draft, status=JobStatus.succeeded,
              result={"draft_id": d.id, "score": 8.2})
    session.add(d)
    session.add(job)
    session.commit()
    _save(session, account, ChatRole.user, "写一篇")
    _save(session, account, ChatRole.tool, "{}", "write_post", {"args": {"hint": "通勤"}, "result": {"ok": True, "job_id": job.id}})
    _save(session, account, ChatRole.assistant, "开始写了")
    llm.push("manager", say("好"))
    await chat(session, llm, account.id, "选第 6 个，然后刚才那篇再改改")
    sent = llm.calls[-1][1]
    tools = {m["tool_call_id"]: m["content"] for m in sent if m["role"] == "tool"}
    bench = next(v for v in tools.values() if "博主6" in v)
    assert "xiaohongshu.com/user/profile/u6" in bench and "很长的理由" not in bench
    assert any("通勤包里的5件小物" in v and "8.2" in v for v in tools.values())


async def test_old_turns_roll_into_long_term_memory(session, llm, account):
    """聊得很长：早的几轮压成要点放进系统提示，最近的原样带；要点滚动更新。"""
    from mediaflow.agents.manager import HISTORY_TURNS, MEMORY_KEEP_TURNS, remember

    _turns(session, account, HISTORY_TURNS + 4)
    llm.push("memory", {"summary": "- 用户是宝妈，晚上 9 点后才有空\n- 不喜欢太鸡汤的文案"})
    assert await remember(session, llm, account.id)
    assert "第0句" in llm.prompts_of("memory")[0] and f"第{HISTORY_TURNS + 3}句" not in llm.prompts_of("memory")[0]
    session.refresh(account)
    assert "宝妈" in account.chat_memory["summary"] and account.chat_memory["upto"]
    assert not await remember(session, llm, account.id)  # 没攒够新的，不再调模型

    llm.push("manager", say("记得，你晚上 9 点后有空"))
    await chat(session, llm, account.id, "我什么时候有空来着")
    sent = llm.calls[-1][1]
    assert "宝妈，晚上 9 点后才有空" in sent[0]["content"]
    texts = " ".join(m.get("content") or "" for m in sent[1:])
    assert "第0句" not in texts and f"第{HISTORY_TURNS + 4 - MEMORY_KEEP_TURNS}句" in texts

    _turns(session, account, HISTORY_TURNS, start=100)
    llm.push("memory", {"summary": "- 用户是宝妈\n- 第100句的事"})
    assert await remember(session, llm, account.id)
    assert "宝妈，晚上 9 点后才有空" in llm.prompts_of("memory")[1]  # 旧要点带进去一起更新


def _coarse_clock(monkeypatch):
    """模拟时钟精度很粗的机器（比如 Windows）：一段时间里每次取到的都是同一个时刻。"""
    from datetime import datetime

    from mediaflow.domain import models

    frozen = datetime.now(models.timezone.utc)

    class Coarse(datetime):
        @classmethod
        def now(cls, tz=None):
            return frozen

    monkeypatch.setattr(models, "datetime", Coarse)


def test_chat_timestamps_are_unique_and_ordered(session, account, monkeypatch):
    """连着存很多条消息，时间戳也不能撞：历史和记忆截断点都按 created_at 排，撞了顺序就乱、消息会被漏掉。"""
    from mediaflow.agents.manager import _save
    from mediaflow.domain.models import ChatMessage

    _coarse_clock(monkeypatch)
    saved = [_save(session, account, ChatRole.user, f"第{i}条").id for i in range(120)]
    rows = session.exec(select(ChatMessage).where(ChatMessage.account_id == account.id)
                        .order_by(ChatMessage.created_at)).all()
    assert len({r.created_at for r in rows}) == len(rows) == 120
    assert [r.id for r in rows] == saved


def test_utcnow_strictly_increases_across_threads(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    from mediaflow.domain.models import utcnow

    _coarse_clock(monkeypatch)
    with ThreadPoolExecutor(8) as ex:
        got = [t for chunk in ex.map(lambda _: [utcnow() for _ in range(500)], range(8)) for t in chunk]
    assert len(set(got)) == len(got)
    assert all(t.tzinfo is not None for t in got)


async def test_snapshot_lists_recent_drafts_topics_and_candidates(session, llm, account):
    from mediaflow.domain.models import Draft

    session.add(Draft(user_id="local", account_id=account.id, title="早八通勤妆", body="b", original_title="t", original_body="b"))
    session.add(Topic(user_id="local", account_id=account.id, title="秋天第一件风衣"))
    account.bench_candidates = {"candidates": [{"name": "穿搭阿梨", "url": "https://www.xiaohongshu.com/user/profile/abc"}]}
    session.add(account)
    session.commit()
    llm.push("manager", say("好"))
    await chat(session, llm, account.id, "在吗")
    system = llm.calls[-1][1][0]["content"]
    assert "早八通勤妆" in system and "秋天第一件风衣" in system and "user/profile/abc" in system
