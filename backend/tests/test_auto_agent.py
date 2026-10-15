"""
自动运营（auto_agent）回归测试

历史 bug：自动运营曾经自己实现了一套「搜选题→生成→存草稿」流水线，
和手动创作走的 AgentRunner 完全是两条路，导致定时产出：
  - 跳过 evaluate_content 质量评估
  - 配图永远停在 placehold.co 占位图（从不触发后台真实生图）
  - 选题不做历史去重

这里锁住修复后的行为：run_account_once 必须走 AgentRunner，
因此质检、去重、真实配图的触发点都在链路上。

不联网：脚本化 AgentRunner._call_llm 的返回，驱动真实的工具链和 DB 写入。
"""
import json

import pytest

from models import XiaohongshuAccount, Content, ContentStatus
from services import auto_agent
from services.agent import core as agent_core


def _tool_call(name: str, args: dict, call_id: str = "c1") -> dict:
    return {
        "id": call_id,
        "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)},
    }


class ScriptedLLM:
    """按顺序吐出预设的 tool_calls，替代真实的 DeepSeek 调用。"""

    def __init__(self, steps):
        self.steps = list(steps)
        self.seen = []           # 记录实际被调用的工具名，用于断言链路

    def __call__(self, messages, tools):
        if not self.steps:
            return {"content": "完成", "tool_calls": []}
        step = self.steps.pop(0)
        self.seen.append(step["function"]["name"])
        return {"content": None, "tool_calls": [step]}


@pytest.fixture
def scripted_agent(monkeypatch, test_account):
    """把 Agent 的 LLM 和联网工具换成可控实现，save_draft 保持真实（要验证落库）。"""

    REF = "draft_fixed"
    script = [
        _tool_call("get_account_history", {"account_id": test_account.id}),
        _tool_call("search_trending", {"keyword": "测试", "theme": test_account.theme}),
        _tool_call("generate_content", {"topic_title": "测试选题", "theme": "测试主题"}),
        _tool_call("evaluate_content", {"draft_ref": REF, "theme": "测试主题"}),
        _tool_call("save_draft", {"account_id": test_account.id, "draft_ref": REF}),
    ]
    llm = ScriptedLLM(script)
    monkeypatch.setattr(agent_core, "chat_completion",
                        lambda messages, tools=None, **kw: llm(messages, tools))

    # 替换会联网的工具；save_draft 保持真实实现以验证落库
    from services.agent import tools as agent_tools

    def fake_generate(store=None, **kw):
        # 按新语义把正文写进服务端暂存区，只回引用
        store[REF] = {
            "title": "测试标题", "content": "测试正文",
            "tags": ["测试"], "image_prompts": [],
            "topic_title": "测试选题", "score": None,
        }
        return {"success": True, "draft_ref": REF, "title": "测试标题",
                "preview": "测试正文", "char_count": 4, "tags": ["测试"], "image_count": 0}

    monkeypatch.setitem(agent_tools.TOOL_HANDLERS, "search_trending",
                        lambda **kw: {"success": True, "count": 1,
                                      "topics": {"items": [{"title": "测试选题"}]}})
    monkeypatch.setitem(agent_tools.TOOL_HANDLERS, "get_account_history",
                        lambda **kw: {"success": True, "recent_titles": ["历史内容A"]})
    monkeypatch.setitem(agent_tools.TOOL_HANDLERS, "generate_content", fake_generate)
    monkeypatch.setitem(agent_tools.TOOL_HANDLERS, "evaluate_content",
                        lambda draft_ref=None, **kw: {
                            "success": True, "score": 9, "verdict": "优秀",
                            "draft_ref": draft_ref, "issues": [], "suggestions": []})
    return llm


def test_run_account_once_goes_through_agent_runner(db_session, test_account, scripted_agent):
    """自动运营必须走 AgentRunner —— 质检与历史去重都在链路上。"""
    result = auto_agent.run_account_once(test_account, db_session, ai_service=None, count=1)

    assert result["success"] is True
    assert result["produced"] == 1

    # 关键回归点：这三个工具必须真的被调到
    assert "get_account_history" in scripted_agent.seen, "选题去重缺失"
    assert "evaluate_content" in scripted_agent.seen, "质量评估被跳过（历史 bug）"
    assert "save_draft" in scripted_agent.seen

    # 评分被带回结果
    assert result["contents"][0]["score"] == 9

    # 草稿真的落库，且挂在正确账号下
    content = db_session.query(Content).filter(
        Content.id == result["contents"][0]["id"]
    ).first()
    assert content is not None
    assert content.account_id == test_account.id
    assert content.status == ContentStatus.draft
    assert content.title == "测试标题"


def test_run_account_once_advances_last_auto_run(db_session, test_account, scripted_agent):
    """跑完要推进 last_auto_run，否则调度器会反复重跑同一账号。"""
    assert test_account.last_auto_run is None
    auto_agent.run_account_once(test_account, db_session, ai_service=None, count=1)
    assert test_account.last_auto_run is not None


def test_run_account_once_requires_theme_or_keywords(db_session, test_user):
    """没有主题也没关键词时应直接失败，而不是让 Agent 瞎跑。"""
    bare = XiaohongshuAccount(id="bare-account", user_id=test_user.id, username="bare")
    db_session.add(bare)
    db_session.commit()

    result = auto_agent.run_account_once(bare, db_session, ai_service=None, count=1)
    assert result["success"] is False
    assert result["produced"] == 0
    assert "主题" in result["error"]


def test_agent_failure_does_not_crash_and_advances_clock(db_session, test_account, monkeypatch):
    """单篇失败要被吞掉并记录，last_auto_run 仍推进（避免失败账号每轮重试）。"""
    def boom(self, account, on_event, **kw):
        raise RuntimeError("LLM 挂了")

    monkeypatch.setattr(agent_core.AgentRunner, "run", boom)

    result = auto_agent.run_account_once(test_account, db_session, ai_service=None, count=1)
    assert result["success"] is False
    assert result["produced"] == 0
    assert "LLM 挂了" in result["error"]
    assert test_account.last_auto_run is not None


def test_run_all_due_accounts_isolates_failures(db_session, test_user, test_account, monkeypatch):
    """一个账号炸了不能中断整轮调度。"""
    good = XiaohongshuAccount(
        id="good-account", user_id=test_user.id, username="good",
        theme="正常主题", auto_enabled=True,
    )
    test_account.auto_enabled = True
    test_account.theme = "会炸的主题"
    db_session.add(good)
    db_session.commit()

    calls = {"n": 0}

    def flaky(account, db, ai_service, count=None):
        calls["n"] += 1
        if account.id == test_account.id:
            raise RuntimeError("这个账号炸了")
        return {"success": True, "produced": 1, "contents": [], "error": None}

    monkeypatch.setattr(auto_agent, "run_account_once", flaky)

    summary = auto_agent.run_all_due_accounts(db_session, ai_service=None)

    assert calls["n"] == 2, "炸掉的账号不应中断后续账号"
    assert summary["ran"] == 2
    statuses = [d["success"] for d in summary["details"]]
    assert True in statuses and False in statuses


def test_should_run_respects_frequency(test_account):
    """频率判断：从未跑过就跑；刚跑完不重复跑。"""
    from datetime import datetime, timedelta

    test_account.auto_enabled = True
    test_account.last_auto_run = None
    assert auto_agent.should_run(test_account) is True

    test_account.auto_frequency = "daily"
    test_account.last_auto_run = datetime.utcnow()
    assert auto_agent.should_run(test_account) is False

    test_account.last_auto_run = datetime.utcnow() - timedelta(days=2)
    assert auto_agent.should_run(test_account) is True

    test_account.auto_enabled = False
    assert auto_agent.should_run(test_account) is False
