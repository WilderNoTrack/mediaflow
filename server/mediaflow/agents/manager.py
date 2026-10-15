"""账号管家「小媒」：对话式配置账号定位、记规则、找选题、派写稿任务。

和 v1 的区别：
- 工具全部绑定当前账号（account_id 由代码注入，模型无法指定别的账号）
- 每次工具调用都作为一条 tool 消息存进对话历史，下一轮对话它记得自己做过什么
- 写稿不在对话里同步跑几分钟，而是派一个后台任务，聊天立刻返回
- 同一账号的对话串行处理，连发两条不会同时改配置
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from typing import Any

from sqlmodel import Session, col, select

from mediaflow.agents.context import load_context
from mediaflow.domain.models import (
    Account, AutoFrequency, ChatMessage, ChatRole, Draft, JobKind, Rule, RuleSource, Trigger, utcnow,
)
from mediaflow.jobs.queue import JobConflict, enqueue
from mediaflow.llm.client import LLM, LLMError
from mediaflow.services.topics import Fetcher, propose_topics

logger = logging.getLogger(__name__)

MAX_STEPS = 8
HISTORY_LIMIT = 40
_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

SYSTEM_PROMPT = """你是「小媒」，MediaFlow 的小红书账号管家，像一个靠谱的运营搭子。
你的工作是帮用户把账号定位聊清楚、记住长期规则、找选题、安排写稿。

【原则】
1. 边聊边记：听到新的定位信息（主题、受众、文案风格、配图风格、选题方向、关键词），马上调用 update_profile 写入，不要攒着。
2. 用户说「以后都要…」「每篇都…」「不要再…」这类长期要求，用 add_rule 记成一条规则；要删就用 remove_rule（规则 ID 见下方账号状态）。
3. 主动补全：定位里还空着的项，自然地问，一次只问一个。配图风格要问出具体的视觉感觉，尽量保留用户原话。
4. 用户想要选题，用 find_topics；想写一篇，用 write_post（可以带选题 ID 或方向）。写稿在后台进行，告诉用户稍后在「草稿」里看。
5. 工具结果里有失败或降级（比如热点来源没抓到），必须如实告诉用户，不能装作正常。
6. 不要在聊天里写整篇文案，那是 write_post 的事。

【风格】中文，自然口语，简短（一般不超过 100 字），改了什么就明确说改了什么。"""


def _tool(name: str, desc: str, props: dict[str, Any] | None = None, required: list[str] | None = None) -> dict:
    return {"type": "function", "function": {
        "name": name, "description": desc,
        "parameters": {"type": "object", "properties": props or {}, "required": required or []},
    }}


TOOLS = [
    _tool("update_profile", "更新账号定位，只传要改的字段。keywords 为完整列表（覆盖）", {
        "theme": {"type": "string", "description": "账号主题"},
        "audience": {"type": "string", "description": "目标受众"},
        "content_style": {"type": "string", "description": "文案风格"},
        "image_style": {"type": "string", "description": "配图视觉风格，尽量保留用户原话"},
        "topic_type": {"type": "string", "description": "选题方向/类别"},
        "keywords": {"type": "array", "items": {"type": "string"}},
        "name": {"type": "string", "description": "账号名称"},
    }),
    _tool("add_rule", "记一条长期规则，以后每篇都会遵守", {"text": {"type": "string"}}, ["text"]),
    _tool("remove_rule", "停用一条长期规则", {"rule_id": {"type": "string"}}, ["rule_id"]),
    _tool("list_drafts", "看最近的草稿（标题、状态、分数）", {"limit": {"type": "integer"}}),
    _tool("find_topics", "搜热点并按账号定位出几个选题，存进选题库", {
        "direction": {"type": "string", "description": "可选：用户指定的方向"},
    }),
    _tool("write_post", "派一个后台任务写一篇稿子（选题→写→质检→配图），写好进草稿待审核", {
        "topic_id": {"type": "string", "description": "可选：选题库里的选题 ID"},
        "hint": {"type": "string", "description": "可选：方向或额外要求"},
    }),
    _tool("set_auto", "开关自动模式（按频率自动写稿进待审核）", {
        "enabled": {"type": "boolean"},
        "frequency": {"type": "string", "enum": ["daily", "every_2_days", "weekly"]},
    }, ["enabled"]),
]

PROFILE_FIELDS = ("name", "theme", "audience", "content_style", "image_style", "topic_type", "keywords")


class Toolbox:
    def __init__(self, session: Session, llm: LLM, account: Account, fetch: Fetcher | None) -> None:
        self.s, self.llm, self.acc, self.fetch = session, llm, account, fetch

    def snapshot(self) -> dict:
        rules = self.s.exec(
            select(Rule).where(Rule.account_id == self.acc.id, Rule.active == True)  # noqa: E712
            .order_by(col(Rule.created_at))
        ).all()
        a = self.acc
        return {
            "name": a.name, "theme": a.theme, "audience": a.audience,
            "content_style": a.content_style, "image_style": a.image_style,
            "topic_type": a.topic_type, "keywords": a.keywords,
            "rules": [{"id": r.id, "text": r.text} for r in rules],
            "auto_enabled": a.auto_enabled, "auto_frequency": a.auto_frequency.value,
        }

    async def call(self, name: str, args: dict) -> dict:
        fn = getattr(self, f"t_{name}", None)
        if fn is None:
            return {"ok": False, "error": f"未知工具 {name}"}
        try:
            return await fn(**args)
        except TypeError as e:
            return {"ok": False, "error": f"参数不对：{e}"}
        except Exception as e:  # noqa: BLE001
            logger.exception("管家工具 %s 出错", name)
            return {"ok": False, "error": str(e)}

    async def t_update_profile(self, **fields) -> dict:
        changed = {}
        for k in PROFILE_FIELDS:
            v = fields.get(k)
            if v is None:
                continue
            if k == "keywords":
                v = [str(x).strip() for x in v if str(x).strip()]
            else:
                v = str(v).strip()
            setattr(self.acc, k, v)
            changed[k] = v
        if not changed:
            return {"ok": False, "error": "没有要改的字段"}
        self.acc.updated_at = utcnow()
        self.s.add(self.acc)
        self.s.commit()
        return {"ok": True, "updated": changed}

    async def t_add_rule(self, text: str) -> dict:
        text = text.strip()
        if not text:
            return {"ok": False, "error": "规则是空的"}
        r = Rule(user_id=self.acc.user_id, account_id=self.acc.id, text=text, source=RuleSource.chat)
        self.s.add(r)
        self.s.commit()
        return {"ok": True, "rule_id": r.id, "text": text}

    async def t_remove_rule(self, rule_id: str) -> dict:
        r = self.s.get(Rule, rule_id)
        if r is None or r.account_id != self.acc.id:
            return {"ok": False, "error": "没有这条规则"}
        r.active = False
        self.s.add(r)
        self.s.commit()
        return {"ok": True, "removed": r.text}

    async def t_list_drafts(self, limit: int = 8) -> dict:
        rows = self.s.exec(
            select(Draft).where(Draft.account_id == self.acc.id)
            .order_by(col(Draft.created_at).desc()).limit(min(int(limit), 20))
        ).all()
        return {"ok": True, "drafts": [
            {"id": d.id, "title": d.title, "status": d.status.value, "score": d.score} for d in rows
        ]}

    async def t_find_topics(self, direction: str = "") -> dict:
        ctx = load_context(self.s, self.acc.id)
        p = await propose_topics(self.s, self.llm, ctx, direction=direction, count=5, fetch=self.fetch)
        out: dict[str, Any] = {"ok": True, "topics": [
            {"id": t.id, "title": t.title, "angle": t.angle, "source": t.source} for t in p.topics
        ]}
        if p.source_note:
            out["source_note"] = p.source_note
        return out

    async def t_write_post(self, topic_id: str = "", hint: str = "") -> dict:
        try:
            job = enqueue(self.s, JobKind.write_draft, user_id=self.acc.user_id, account_id=self.acc.id,
                          payload={"topic_id": topic_id or None, "hint": hint, "trigger": Trigger.chat.value})
        except JobConflict as e:
            return {"ok": False, "error": str(e), "job_id": e.job.id}
        return {"ok": True, "job_id": job.id, "note": "已开始在后台写，1-3 分钟后在草稿里能看到"}

    async def t_set_auto(self, enabled: bool, frequency: str | None = None) -> dict:
        self.acc.auto_enabled = bool(enabled)
        if frequency in AutoFrequency.__members__:
            self.acc.auto_frequency = AutoFrequency(frequency)
        self.acc.updated_at = utcnow()
        self.s.add(self.acc)
        self.s.commit()
        return {"ok": True, "auto_enabled": self.acc.auto_enabled, "frequency": self.acc.auto_frequency.value}


def _history(session: Session, account_id: str) -> list[dict]:
    rows = list(reversed(session.exec(
        select(ChatMessage).where(ChatMessage.account_id == account_id)
        .order_by(col(ChatMessage.created_at).desc()).limit(HISTORY_LIMIT)
    ).all()))
    msgs: list[dict] = []
    for m in rows:
        if m.role == ChatRole.tool:
            # 把做过的操作作为管家自己的备忘放回上下文
            msgs.append({"role": "assistant", "content": f"（我执行了 {m.tool_name}：{m.content}）"})
        else:
            msgs.append({"role": m.role.value, "content": m.content})
    return msgs


def _save(session: Session, acc: Account, role: ChatRole, content: str, tool_name: str = "", payload: dict | None = None) -> ChatMessage:
    m = ChatMessage(user_id=acc.user_id, account_id=acc.id, role=role, content=content,
                    tool_name=tool_name, payload=payload or {})
    session.add(m)
    session.commit()
    session.refresh(m)
    return m


async def chat(session: Session, llm: LLM, account_id: str, text: str, *, fetch: Fetcher | None = None) -> list[ChatMessage]:
    """处理一条用户消息，返回本轮新增的消息（用户消息、工具记录、回复）。"""
    async with _locks[account_id]:
        acc = session.get(Account, account_id)
        if acc is None:
            raise LookupError("账号不存在")
        box = Toolbox(session, llm, acc, fetch)
        history = _history(session, account_id)
        new: list[ChatMessage] = [_save(session, acc, ChatRole.user, text)]

        messages: list[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT + "\n\n【当前账号状态】\n"
             + json.dumps(box.snapshot(), ensure_ascii=False, indent=1)},
            *history,
            {"role": "user", "content": text},
        ]
        reply = ""
        for _ in range(MAX_STEPS):
            try:
                resp = await llm.complete(messages, tools=TOOLS, temperature=0.6)
            except LLMError as e:
                reply = f"我这边连不上 AI 服务（{e}），这句话已经记下了，稍后再试一次？"
                break
            if not resp.tool_calls:
                reply = resp.content.strip() or "嗯？我没太明白，可以再说一次吗"
                break
            messages.append({"role": "assistant", "content": resp.content or None, "tool_calls": [
                {"id": c.id, "type": "function",
                 "function": {"name": c.name, "arguments": json.dumps(c.arguments, ensure_ascii=False)}}
                for c in resp.tool_calls
            ]})
            for c in resp.tool_calls:
                result = await box.call(c.name, c.arguments)
                summary = json.dumps(result, ensure_ascii=False)[:1500]
                new.append(_save(session, acc, ChatRole.tool, summary, tool_name=c.name,
                                 payload={"args": c.arguments, "result": result}))
                messages.append({"role": "tool", "tool_call_id": c.id, "content": summary})
        else:
            reply = "这一轮操作有点多，我先停一下，刚才做的都已保存。"
        new.append(_save(session, acc, ChatRole.assistant, reply))
        return new
