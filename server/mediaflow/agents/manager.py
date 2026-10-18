"""账号管家「小媒」：对话式配置账号定位、记规则、找选题、派写稿任务。

和 v1 的区别：
- 工具全部绑定当前账号（account_id 由代码注入，模型无法指定别的账号）
- 每次工具调用都作为一条 tool 消息存进对话历史，下一轮对话它记得自己做过什么
- 写稿不在对话里同步跑几分钟，而是派一个后台任务，聊天立刻返回
- 同一账号的对话串行处理，连发两条不会同时改配置
- 调研工具（搜内容/搜博主/看作品/看详情）只读、可并行；结论用 save_note 存成运营笔记，写稿时参考
  设计依据见 docs/agent-architecture.md
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
    Account, AutoFrequency, ChatMessage, ChatRole, Draft, JobKind, Note, Rule, RuleSource, Trigger, utcnow,
)
from mediaflow.jobs.queue import JobConflict, enqueue
from mediaflow.llm.client import LLM, LLMError
from mediaflow.research import service as research
from mediaflow.research.types import Unsupported
from mediaflow.services.topics import Fetcher, propose_topics

logger = logging.getLogger(__name__)

MAX_STEPS = 12
HISTORY_LIMIT = 40
RESULT_CHARS = 1500          # 普通工具结果给模型看的长度上限
RESEARCH_RESULT_CHARS = 4000  # 调研结果信息密度高，放宽
HISTORY_TOOL_CHARS = 500      # 历史轮次里的工具结果只留摘要，控制上下文
READ_ONLY = {"list_drafts", "find_benchmarks", "research_search", "research_creators", "research_creator_posts", "research_post"}
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

【调研】用户想了解某个博主、某类爆款、某个话题在各平台的情况时，用 research_* 工具查真实数据。
- 先宽后窄：research_search 看话题全貌，或 research_creators 先确认是哪位博主（重名时挑名字最吻合、粉丝最多的，拿不准就问用户），
  再 research_creator_posts 看作品（sort=top 看爆款、latest 看近况），最后挑 2-3 篇最有代表性的 research_post 看正文、标签和热评。
- 预算：简单问题 1-3 次调用；分析一个博主 5-10 次；不要为了凑数多查。互不依赖的调用在同一步一起发出（会并行执行）。
- ref（如 xhs:c3、dy:p12）原样传回即可，不要编造；提示 ref 失效就重新搜。
- 结论必须来自工具数据，引用具体标题和数字；拿不到的写「没有公开数据」，绝不编造粉丝数、阅读量。
- 工具报「没登录/不支持」时如实告诉用户，并说明去「数据来源」里配置，或换个支持的平台。
- 分析博主（对标分析）按这个结构回复：①账号概况（定位、粉丝、更新频率）②内容结构（常做的栏目/形式）
  ③爆款规律（选题、标题写法、开头钩子、标签）④评论区用户在关心什么 ⑤给本账号的 3 条可执行建议。
- 分析完用 save_note 存一份精炼要点（400 字内，偏「可借鉴的做法」），告诉用户已存为运营笔记、之后写稿会参考，不需要可以删。

【对标账号】用户想照着别人的路子做（「对标」「复刻」「照着某某做」「按这个博主的路子起号」），一个账号最多同时对标 3 个：
- 用户给了链接、名字或小红书号：直接 clone_creator（targets 原样传，可以一次传多个）。
- 用户只说了方向、没指定是谁（「帮我找几个做穿搭的号」）：用 find_benchmarks 找同领域、有爆款的博主。
  结果会以卡片形式展示给用户勾选，你不用逐个复述，只用两三句话点出最值得学的 1-2 个和理由，
  然后说「勾选后点『学习选中的』，或者直接告诉我选哪几个」。用户说「选第 1 和第 3 个」就把对应的 url 传给 clone_creator。
  用户说「再找一批」「要粉丝少一点的」就再调 find_benchmarks，把要求写进 prefer。
- 默认只找同领域；用户明确要跨领域借鉴（比如「学美妆博主的标题写法」）才放宽，写进 prefer。
- 主题还不知道就先问一句。clone_creator 会在后台读作品、逐个拆打法，再把几个人的打法合成一套、换成用户的主题，
  自动更新账号定位、写法规则和选题库，每个账号大约 1 分钟，告诉用户去「对标」页看。
- 账号状态里的 benchmarks 是已经在对标的账号；用户问「对标的打法是什么」直接按账号定位里的【对标账号打法】回答。

【风格】中文，自然口语，不用 Markdown（不要 ** 加粗、# 标题），简短（一般不超过 100 字；调研分析可以长一些，但要分点、去水分），改了什么就明确说改了什么。"""


def _tool(name: str, desc: str, props: dict[str, Any] | None = None, required: list[str] | None = None) -> dict:
    return {"type": "function", "function": {
        "name": name, "description": desc,
        "parameters": {"type": "object", "properties": props or {}, "required": required or []},
    }}


def _platforms_with(cap: str) -> list[str]:
    return [p for p, caps in research.capabilities().items() if cap in caps]


def _research_tools() -> list[dict]:
    labels = research.PLATFORM_LABELS
    creator_ps = _platforms_with("搜博主")
    names = "、".join(f"{labels[p]}({p})" for p in creator_ps)
    return [
        _tool("research_search", "按关键词搜各平台的内容（标题、热度、链接），不传 platform 就全平台一起搜。"
              "结果里带 ref 的可以接着用 research_post 看详情", {
                  "keyword": {"type": "string"},
                  "platform": {"type": "string", "enum": list(labels), "description": "可选：只搜一个平台"},
              }, ["keyword"]),
        _tool("research_creators", f"按名字搜博主，返回粉丝数、简介和 ref。支持：{names}。公众号没有粉丝数", {
            "platform": {"type": "string", "enum": creator_ps},
            "name": {"type": "string", "description": "博主名字，去掉表情和后缀更容易搜到"},
        }, ["platform", "name"]),
        _tool("research_creator_posts", "看博主最近的作品列表（标题、日期、互动数据）和更新频率、互动中位数", {
            "creator_ref": {"type": "string", "description": "research_creators 返回的 ref，如 xhs:c3"},
            "limit": {"type": "integer", "description": "列几条，默认 10，最多 20"},
            "sort": {"type": "string", "enum": ["latest", "top"], "description": "latest 按时间；top 按互动从高到低"},
        }, ["creator_ref"]),
        _tool("research_post", "看一篇作品的详情：正文、标签、完整互动数据、高赞评论", {
            "post_ref": {"type": "string", "description": "作品 ref，如 xhs:p12"},
        }, ["post_ref"]),
    ]


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
    *_research_tools(),
    _tool("save_note", "存一条运营笔记（调研结论、对标账号要点、爆款规律等），之后写稿和出选题会参考", {
        "title": {"type": "string", "description": "简短标题，如「对标：程十安an」"},
        "content": {"type": "string", "description": "要点，400 字以内"},
    }, ["title", "content"]),
    _tool("remove_note", "删除一条运营笔记（ID 见账号状态）", {"note_id": {"type": "string"}}, ["note_id"]),
    _tool("find_benchmarks", "按方向找同领域、有爆款的小红书博主当对标候选（带粉丝、点赞中位数、爆款率、值得学的地方），"
          "结果会以可勾选的卡片展示给用户。大约半分钟到一分钟", {
              "query": {"type": "string", "description": "方向，如「通勤穿搭」；不传用账号主题"},
              "prefer": {"type": "string", "description": "可选：用户的额外要求，如「粉丝少一点」「要做视频的」"},
          }),
    _tool("clone_creator", "对标 1-3 个小红书账号：后台读作品、逐个拆打法、合成一套并换成新主题，自动更新定位/规则/选题库", {
        "targets": {"type": "array", "items": {"type": "string"},
                    "description": "对标账号列表：主页链接、笔记链接、博主名字或小红书号，原样传"},
        "theme": {"type": "string", "description": "用户想换成的主题；用户没说且账号已有主题时可以不传"},
    }, ["targets"]),
]

PROFILE_FIELDS = ("name", "theme", "audience", "content_style", "image_style", "topic_type", "keywords")


def _bench_state(s: Session, account_id: str) -> dict:
    from mediaflow.services.benchmark import listing

    rows = listing(s, account_id)
    if not rows:
        return {}
    return {"benchmarks": [{"id": b.id, "creator": b.creator_name or b.target, "status": b.status.value,
                            **({"error": b.error} if b.error else {})} for b in rows]}


class Toolbox:
    def __init__(self, session: Session, llm: LLM, account: Account, fetch: Fetcher | None) -> None:
        self.s, self.llm, self.acc, self.fetch = session, llm, account, fetch

    def snapshot(self) -> dict:
        rules = self.s.exec(
            select(Rule).where(Rule.account_id == self.acc.id, Rule.active == True)  # noqa: E712
            .order_by(col(Rule.created_at))
        ).all()
        notes = self.s.exec(select(Note).where(Note.account_id == self.acc.id)
                            .order_by(col(Note.created_at).desc()).limit(20)).all()
        a = self.acc
        return {
            "notes": [{"id": n.id, "title": n.title} for n in notes],
            "name": a.name, "theme": a.theme, "audience": a.audience,
            "content_style": a.content_style, "image_style": a.image_style,
            "topic_type": a.topic_type, "keywords": a.keywords,
            "rules": [{"id": r.id, "text": r.text} for r in rules],
            "auto_enabled": a.auto_enabled, "auto_frequency": a.auto_frequency.value,
            **_bench_state(self.s, a.id),
        }

    async def call(self, name: str, args: dict) -> dict:
        fn = getattr(self, f"t_{name}", None)
        if fn is None:
            return {"ok": False, "error": f"未知工具 {name}"}
        try:
            return await fn(**args)
        except TypeError as e:
            return {"ok": False, "error": f"参数不对：{e}"}
        except (Unsupported, LookupError) as e:
            return {"ok": False, "error": str(e)}
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

    async def t_find_benchmarks(self, query: str = "", prefer: str = "") -> dict:
        from mediaflow.services import benchmark as bench

        rows = bench.listing(self.s, self.acc.id)
        have = [x for b in rows for x in (b.creator_name, b.target) if x]
        out = await bench.find_candidates(self.llm, query.strip() or self.acc.theme, prefer=prefer,
                                          keywords=self.acc.keywords, exclude=have)
        return {"ok": True, **out, "slots_left": bench.MAX_BENCH - len(rows)}

    async def t_clone_creator(self, targets: list[str] | str = "", theme: str = "", target: str = "") -> dict:
        from mediaflow.services import benchmark as bench

        items = [targets] if isinstance(targets, str) else list(targets or [])
        try:
            job, new = bench.add(self.s, self.acc, [*items, target], theme=theme)
        except JobConflict as e:
            return {"ok": False, "error": str(e), "job_id": e.job.id}
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True, "job_id": job.id, "added": [b.target for b in new],
                "note": f"已开始拆解 {len(new)} 个账号，每个大约 1 分钟，好了在「对标」页看方案，账号定位和选题库会自动更新"}

    async def t_set_auto(self, enabled: bool, frequency: str | None = None) -> dict:
        self.acc.auto_enabled = bool(enabled)
        if frequency in AutoFrequency.__members__:
            self.acc.auto_frequency = AutoFrequency(frequency)
        self.acc.updated_at = utcnow()
        self.s.add(self.acc)
        self.s.commit()
        return {"ok": True, "auto_enabled": self.acc.auto_enabled, "frequency": self.acc.auto_frequency.value}


    # ---- 调研（只读，可并行）----

    async def t_research_search(self, keyword: str, platform: str = "") -> dict:
        keyword = keyword.strip()
        if not keyword:
            return {"ok": False, "error": "关键词是空的"}
        if platform:
            from mediaflow.sources.platforms import ALL_SOURCES
            from mediaflow.sources.registry import fetch_all

            srcs = [x for x in ALL_SOURCES if x.name == platform]
            if not srcs:
                return {"ok": False, "error": f"不认识的平台 {platform}"}
            report = await fetch_all(keyword, 10, sources=srcs)
        elif self.fetch is not None:
            report = await self.fetch(keyword, 6)
        else:
            from mediaflow.sources.registry import fetch_all
            report = await fetch_all(keyword, 6)
        items = []
        for it in report.items:
            d = {"src": it.source, "title": it.title, "heat": it.heat}
            ref = research.item_ref(it.source, it.ref) if it.ref else ""
            if ref:
                d["ref"] = ref
            if it.kind == "hot":
                d["note"] = "热榜兜底，非搜索结果"
            if it.url and len(it.url) <= 120:
                d["url"] = it.url
            items.append({k: v for k, v in d.items() if v})
        out: dict[str, Any] = {"ok": True, "items": items}
        problems = [f"{st.label}：{st.note}" for st in report.statuses if st.note]
        if problems:
            out["source_notes"] = problems
        return out

    async def t_research_creators(self, platform: str, name: str) -> dict:
        return {"ok": True, **await research.search_creators(platform, name.strip(), 5)}

    async def t_research_creator_posts(self, creator_ref: str, limit: int = 10, sort: str = "latest") -> dict:
        return {"ok": True, **await research.creator_posts(creator_ref.strip(), int(limit), sort)}

    async def t_research_post(self, post_ref: str) -> dict:
        return {"ok": True, **await research.post_detail(post_ref.strip())}

    # ---- 运营笔记 ----

    async def t_save_note(self, title: str, content: str) -> dict:
        title, content = title.strip()[:60], content.strip()[:2000]
        if not title or not content:
            return {"ok": False, "error": "标题和内容都不能空"}
        n = Note(user_id=self.acc.user_id, account_id=self.acc.id, title=title, content=content)
        self.s.add(n)
        self.s.commit()
        return {"ok": True, "note_id": n.id, "title": title}

    async def t_remove_note(self, note_id: str) -> dict:
        n = self.s.get(Note, note_id)
        if n is None or n.account_id != self.acc.id:
            return {"ok": False, "error": "没有这条笔记"}
        self.s.delete(n)
        self.s.commit()
        return {"ok": True, "removed": n.title}


def _history(session: Session, account_id: str) -> list[dict]:
    rows = list(reversed(session.exec(
        select(ChatMessage).where(ChatMessage.account_id == account_id)
        .order_by(col(ChatMessage.created_at).desc()).limit(HISTORY_LIMIT)
    ).all()))
    msgs: list[dict] = []
    for m in rows:
        if m.role == ChatRole.tool:
            # 把做过的操作作为管家自己的备忘放回上下文
            body = m.content if len(m.content) <= HISTORY_TOOL_CHARS else m.content[:HISTORY_TOOL_CHARS] + "…（已截断）"
            msgs.append({"role": "assistant", "content": f"（我执行了 {m.tool_name}：{body}）"})
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


async def _run_calls(box: Toolbox, calls: list) -> list[dict]:
    """同一步的多个工具调用：只读的并行跑，会改数据的按顺序跑（共用一个数据库 session）。"""
    write_lock = asyncio.Lock()

    async def one(c) -> dict:
        if c.error:
            return {"ok": False, "error": c.error + "。请修正参数后重新调用。"}
        if c.name in READ_ONLY:
            return await box.call(c.name, c.arguments)
        async with write_lock:
            return await box.call(c.name, c.arguments)

    return list(await asyncio.gather(*(one(c) for c in calls)))


def _for_model(name: str, result: dict) -> dict:
    """候选卡片里的头像、链接只给界面用，模型看精简版（链接留着，选中后要传给 clone_creator）。"""
    if name != "find_benchmarks" or not result.get("candidates"):
        return result
    keep = ("name", "url", "fans", "median_likes", "hit_rate", "per_week", "last_post", "level", "reason", "learn")
    return {**result, "candidates": [
        {"no": i + 1, **{k: c[k] for k in keep if c.get(k) not in (None, "")}} for i, c in enumerate(result["candidates"])
    ]}


def _clip(result: dict, limit: int) -> str:
    text = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
    return text if len(text) <= limit else text[:limit] + "…（结果太长已截断）"


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
            results = await _run_calls(box, resp.tool_calls)
            for c, result in zip(resp.tool_calls, results):
                wide = c.name.startswith("research_") or c.name == "find_benchmarks"
                summary = _clip(_for_model(c.name, result), RESEARCH_RESULT_CHARS if wide else RESULT_CHARS)
                new.append(_save(session, acc, ChatRole.tool, summary, tool_name=c.name,
                                 payload={"args": c.arguments, "result": result}))
                messages.append({"role": "tool", "tool_call_id": c.id, "content": summary})
        else:
            # 步数用完：不再给工具，让模型基于已做的操作给用户一个交代（类似 Agents SDK 的 max_turns 收尾）
            messages.append({"role": "user", "content": "（系统：本轮工具调用次数已达上限，请不要再调用工具，"
                             "直接用一两句话告诉用户刚才做了什么、还有什么没做完。）"})
            try:
                reply = (await llm.complete(messages, temperature=0.3)).content.strip()
            except LLMError:
                reply = ""
            reply = reply or "这一轮操作有点多，我先停一下，刚才做的都已保存。"
        new.append(_save(session, acc, ChatRole.assistant, reply))
        return new
