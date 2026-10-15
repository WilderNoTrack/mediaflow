"""
ManagerAgent — 账号管家（对话式 ReAct Agent）

和内容创作 Agent (core.AgentRunner) 的关系：
  - ManagerAgent 面向"账号"：通过对话理解用户想做什么账号，
    直接读写账号配置、管理自动运营、查看内容情况
  - 需要产出内容时，通过 create_post 工具把 AgentRunner 当子 Agent 调用，
    子 Agent 的进度事件以 agent_progress 包装后转发到同一条 SSE 流

整个 Agent 同步运行（由 router 放入线程池），事件通过 on_event 回调推送。
对话历史持久化在 AccountConversation 表（由 router 负责写入）。
"""

import json
import logging

from sqlalchemy.orm import Session
from typing import Callable

from services.agent.tools import (
    ToolDef,
    SEARCH_TRENDING_DEF,
    handle_search_trending,
)
from services.agent.core import AgentRunner
from services.agent.llm import chat_completion, TokenCounter, LLMError

logger = logging.getLogger(__name__)

MAX_STEPS = 10  # 单轮对话内最多工具步数

MANAGER_SYSTEM_PROMPT = """你是小媒，MediaFlow 的小红书账号管家。你负责帮用户把一个小红书账号从想法做成持续运营的账号。

你的能力（工具）：
- get_account_profile: 查看账号当前完整配置、自动运营状态、内容统计
- update_account_profile: 修改账号定位配置（主题/受众/风格/配图/选题类型/关键词/要求）
- list_recent_contents: 查看账号最近的内容（标题/状态/时间）
- set_auto_operation: 开启/关闭自动运营，设置频率
- search_trending: 搜索多平台热点，找选题方向
- create_post: 立即执行一次完整内容创作（选题→生成→质检→存草稿+配图），耗时约1-3分钟

【核心原则】
1. 边聊边做：用户描述账号想法时，每当你理解了新信息，立刻调用 update_account_profile 写入，不要攒到最后。用户说"美式街头穿搭，给大学生看的"，你就马上更新 theme 和 target_audience。
2. 先看再改：修改配置前如果不清楚当前状态，先 get_account_profile。requirements 和 keywords 是完整列表覆盖式更新——增删时先读当前值，传完整的新列表。
3. 主动补全定位：一个能运营起来的账号需要这些配置齐全——theme（主题）、target_audience（受众）、content_style（文案风格）、image_style（配图视觉风格）、topic_type（每篇围绕什么类别选题）。哪些还空着，就自然地问，每次只问一个问题。其中 image_style 很重要：要问出视觉感觉（如"手机随手拍的生活感"/"专业摄影精致感"/"卡通插画"），用户原话保留。
4. 用户提出长期规则（如"以后所有帖子都要XX"/"封面图必须XX"），写入 requirements 或 image_style，并告诉用户已经记住、以后每篇都会生效。
5. 用户说"发一篇试试"/"帮我生成内容"之类，先确认配置基本齐全（至少有 theme），然后调 create_post。配置太空时建议先聊定位。
6. 用户问"账号现在怎么样"，用 get_account_profile + list_recent_contents 回答。
7. 诚实汇报兜底情况：工具结果中如果出现 fallback、fallback_note、fallback_reason 或错误信息
   （例如：热点搜索降级为 AI 模拟、质量评估服务失败按默认通过、部分图片生成失败），
   必须在回复里明确告诉用户发生了什么、系统用了什么兜底方案、对结果有什么影响。
   绝不允许隐瞒失败、装作一切正常。

【对话风格】
- 中文，轻松自然，像靠谱的运营搭子，不要客服腔
- 回复简短（一般不超过100字），一次只推进一件事
- 做了修改就明确说改了什么，让用户随时知道账号配置的状态
- 不要在聊天里写完整文案/帖子正文，那是 create_post 的工作"""


# ─── 管家工具定义 ─────────────────────────────────────────────────────────────

GET_PROFILE_DEF = ToolDef(
    name="get_account_profile",
    description="获取账号当前完整配置（定位/风格/要求）、自动运营状态和内容统计",
    parameters={"type": "object", "properties": {}, "required": []},
)

UPDATE_PROFILE_DEF = ToolDef(
    name="update_account_profile",
    description="更新账号定位配置，只传需要修改的字段。keywords/requirements 是完整列表覆盖更新",
    parameters={
        "type": "object",
        "properties": {
            "theme":           {"type": "string", "description": "账号主题，如「美式街头穿搭」"},
            "target_audience": {"type": "string", "description": "目标受众"},
            "content_style":   {"type": "string", "description": "文案风格调性（不含图片描述）"},
            "image_style":     {"type": "string", "description": "配图视觉风格完整描述，含结构和感觉，用户原话尽量保留"},
            "topic_type":      {"type": "string", "description": "每篇帖子围绕的选题类别，如「穿搭场景」「菜品名」"},
            "keywords":        {"type": "array", "items": {"type": "string"}, "description": "具体选题词列表（覆盖式）"},
            "requirements":    {"type": "array", "items": {"type": "string"}, "description": "长期文案要求/禁忌列表（覆盖式），每篇生成都会遵守"},
        },
        "required": [],
    },
)

LIST_CONTENTS_DEF = ToolDef(
    name="list_recent_contents",
    description="查看账号最近的内容列表（标题/状态/创建时间）",
    parameters={
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "description": "条数，默认8"},
        },
        "required": [],
    },
)

SET_AUTO_DEF = ToolDef(
    name="set_auto_operation",
    description="开启或关闭自动运营（定时自动创作内容），可设置频率",
    parameters={
        "type": "object",
        "properties": {
            "enabled":   {"type": "boolean", "description": "是否开启"},
            "frequency": {"type": "string", "enum": ["daily", "every_2_days", "weekly"], "description": "频率：每天/每两天/每周"},
        },
        "required": ["enabled"],
    },
)

CREATE_POST_DEF = ToolDef(
    name="create_post",
    description="立即为账号执行一次完整内容创作流程（找选题→生成→质量评估→保存草稿并后台配图），耗时1-3分钟。基于当前账号配置运行",
    parameters={
        "type": "object",
        "properties": {
            "topic_hint": {"type": "string", "description": "可选：用户指定的选题方向提示"},
        },
        "required": [],
    },
)

MANAGER_TOOL_DEFS = [
    GET_PROFILE_DEF,
    UPDATE_PROFILE_DEF,
    LIST_CONTENTS_DEF,
    SET_AUTO_DEF,
    CREATE_POST_DEF,
    SEARCH_TRENDING_DEF,
]


# ─── 工具实现（持有 ctx：db / account / ai_service / on_event）────────────────

class ManagerToolbox:
    def __init__(self, db: Session, account, ai_service, on_event: Callable[[dict], None]):
        self.db         = db
        self.account    = account
        self.ai_service = ai_service
        self.on_event   = on_event

    def dispatch(self, name: str, args: dict) -> dict:
        handlers = {
            "get_account_profile":    self.get_account_profile,
            "update_account_profile": self.update_account_profile,
            "list_recent_contents":   self.list_recent_contents,
            "set_auto_operation":     self.set_auto_operation,
            "create_post":            self.create_post,
            "search_trending":        self.search_trending,
        }
        handler = handlers.get(name)
        if handler is None:
            return {"success": False, "error": f"未知工具: {name}"}
        try:
            return handler(**args)
        except TypeError as e:
            return {"success": False, "error": f"参数错误: {e}"}
        except Exception as e:
            logger.error(f"[Manager:Tool:{name}] {e}")
            return {"success": False, "error": str(e)}

    # ── 工具们 ────────────────────────────────────────────────────────────────

    def get_account_profile(self, **_) -> dict:
        from models import Content
        acc = self.account
        total = self.db.query(Content).filter(Content.account_id == acc.id).count()
        return {
            "success": True,
            "username":        acc.username,
            "theme":           acc.theme,
            "target_audience": acc.target_audience,
            "content_style":   acc.content_style,
            "image_style":     acc.image_style,
            "topic_type":      acc.topic_type,
            "keywords":        acc.keywords or [],
            "requirements":    acc.requirements or [],
            "auto_enabled":    bool(acc.auto_enabled),
            "auto_frequency":  acc.auto_frequency,
            "content_count":   total,
        }

    def update_account_profile(self, **fields) -> dict:
        from datetime import datetime
        acc = self.account
        allowed = {"theme", "target_audience", "content_style", "image_style",
                   "topic_type", "keywords", "requirements"}
        changed = {}
        for k, v in fields.items():
            if k in allowed and v is not None:
                setattr(acc, k, v)
                changed[k] = v
        if not changed:
            return {"success": False, "error": "没有提供可更新的字段"}
        acc.updated_at = datetime.utcnow()
        self.db.commit()
        self.on_event({"type": "profile_updated", "fields": list(changed.keys())})
        logger.info(f"[Manager] 账号 {acc.id} 配置更新: {list(changed.keys())}")
        return {"success": True, "updated": changed}

    def list_recent_contents(self, limit: int = 8, **_) -> dict:
        from models import Content
        rows = (
            self.db.query(Content)
            .filter(Content.account_id == self.account.id)
            .order_by(Content.created_at.desc())
            .limit(min(limit, 20))
            .all()
        )
        return {
            "success": True,
            "contents": [
                {
                    "title":      c.title,
                    "status":     c.status.value if c.status else "draft",
                    "created_at": c.created_at.strftime("%m-%d %H:%M") if c.created_at else "",
                }
                for c in rows
            ],
            "count": len(rows),
        }

    def set_auto_operation(self, enabled: bool, frequency: str = None, **_) -> dict:
        from datetime import datetime
        acc = self.account
        acc.auto_enabled = enabled
        if frequency in ("daily", "every_2_days", "weekly"):
            acc.auto_frequency = frequency
        acc.updated_at = datetime.utcnow()
        self.db.commit()
        self.on_event({"type": "profile_updated", "fields": ["auto_enabled"]})
        freq_label = {"daily": "每天", "every_2_days": "每两天", "weekly": "每周"}.get(acc.auto_frequency, acc.auto_frequency)
        return {
            "success": True,
            "auto_enabled": enabled,
            "auto_frequency": acc.auto_frequency,
            "message": f"自动运营已{'开启，频率：' + freq_label if enabled else '关闭'}",
        }

    def create_post(self, topic_hint: str = "", **_) -> dict:
        def forward(ev: dict) -> None:
            self.on_event({"type": "agent_progress", "event": ev})

        runner = AgentRunner(db=self.db, ai_service=self.ai_service)
        # topic_hint 走参数传递，绝不能临时改 account.keywords：
        # AgentRunner 内部（save_draft）会 db.commit()，脏值会被一并刷进库，
        # 导致用户每提一次「写篇关于X的」，X 就永久混进账号选题词。
        return runner.run(
            account=self.account,
            on_event=forward,
            topic_hint=topic_hint,
            trigger="manager",
        )

    def search_trending(self, **args) -> dict:
        args.setdefault("theme", self.account.theme or "")
        args.setdefault("target_audience", self.account.target_audience or "")
        return handle_search_trending(**args)


# ─── ManagerAgent 主体 ────────────────────────────────────────────────────────

def _strip_options(text: str) -> str:
    """去掉旧版小媒消息里的【OPTIONS】标记，避免污染新 Agent 的上下文。"""
    if "【OPTIONS】" in text:
        return text.split("【OPTIONS】", 1)[0].strip()
    return text


class ManagerAgent:
    """对话式账号管家，单轮 chat() = 一次 ReAct 循环直到产出文本回复。"""

    def __init__(self, db: Session, ai_service=None):
        self.db         = db
        self.ai_service = ai_service
        self.counter    = TokenCounter()

    def chat(self, account, user_message: str, on_event: Callable[[dict], None]) -> str:
        from models import AccountConversation

        toolbox = ManagerToolbox(self.db, account, self.ai_service, on_event)
        tool_schemas = [t.to_openai_schema() for t in MANAGER_TOOL_DEFS]

        # 账号现状快照，让 Agent 不用每轮都先查一遍
        snapshot = toolbox.get_account_profile()
        snapshot.pop("success", None)

        # 加载持久化对话历史（最近24条）
        history_rows = (
            self.db.query(AccountConversation)
            .filter(AccountConversation.account_id == account.id)
            .order_by(AccountConversation.created_at.desc())
            .limit(24)
            .all()
        )
        history = [
            {"role": m.role.value, "content": _strip_options(m.message)[:2000]}
            for m in reversed(history_rows)
        ]

        messages = (
            [{
                "role": "system",
                "content": MANAGER_SYSTEM_PROMPT
                + "\n\n【当前账号状态】\n"
                + json.dumps(snapshot, ensure_ascii=False, indent=2),
            }]
            + history
            + [{"role": "user", "content": user_message}]
        )

        for step in range(MAX_STEPS):
            try:
                response = self._call_llm(messages, tool_schemas)
            except LLMError as e:
                logger.error(f"[Manager] LLM 调用失败: {e}")
                on_event({"type": "error", "message": f"AI 服务暂时不可用：{e}"})
                return "我这边连不上 AI 服务，刚才的操作可能没完成，稍后再试一次？"

            tool_calls = response.get("tool_calls") or []

            if not tool_calls:
                return response.get("content") or "（我有点没想明白，再说一次？）"

            messages.append({
                "role": "assistant",
                "content": response.get("content"),
                "tool_calls": tool_calls,
            })

            for tc in tool_calls:
                fn           = tc.get("function", {})
                tool_name    = fn.get("name", "")
                tool_call_id = tc.get("id", f"call_{step}")
                try:
                    args = json.loads(fn.get("arguments", "{}"))
                except json.JSONDecodeError:
                    args = {}

                on_event({"type": "tool_call", "tool": tool_name, "args": args})
                result = toolbox.dispatch(tool_name, args)
                on_event({"type": "tool_result", "tool": tool_name,
                          "success": result.get("success", True)})

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": json.dumps(result, ensure_ascii=False)[:6000],
                })

        return "这轮操作有点多，我先停一下。刚才的进度都已保存，你可以继续说。"

    def _call_llm(self, messages: list, tools: list) -> dict:
        return chat_completion(
            messages, tools=tools, temperature=0.7, counter=self.counter,
        )
