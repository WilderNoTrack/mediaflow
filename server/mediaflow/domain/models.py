"""数据模型（数据库表）。

设计约定：
- 所有业务表都带 user_id，本地版只有一个默认用户，以后做多用户/SaaS 不用改表结构。
- 长期规则（Rule）单独成表，而不是账号上的 JSON 列表：增删单条不会互相覆盖，
  还能记录来源（用户手写 / 对话中记下 / 从修改中学到）。
- 草稿保留「生成原稿」快照（original_*），用于对比用户修改、学习口味。
"""

import threading
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def _id() -> str:
    return uuid4().hex


_clock_lock = threading.Lock()
_last_now: datetime | None = None


def utcnow() -> datetime:
    """当前 UTC 时间，同一进程里严格递增：连着取到同一个时刻（时钟精度不够、或被往回调）时，
    就在上一次的基础上加 1 微秒。聊天记录、长期记忆的截断点都按 created_at 排序，时间相同顺序就乱了。"""
    global _last_now
    now = datetime.now(timezone.utc)
    with _clock_lock:
        if _last_now is not None and now <= _last_now:
            now = _last_now + timedelta(microseconds=1)
        _last_now = now
    return now


def json_col() -> Any:
    return Field(default_factory=list, sa_column=Column(JSON, nullable=False))


def json_obj_col() -> Any:
    return Field(default_factory=dict, sa_column=Column(JSON, nullable=False))


LOCAL_USER_ID = "local"


# ─── 枚举 ────────────────────────────────────────────────────────────────────


class AutoFrequency(str, Enum):
    daily = "daily"
    every_2_days = "every_2_days"
    weekly = "weekly"


class RuleSource(str, Enum):
    user = "user"  # 用户在设置里手写
    chat = "chat"  # 管家在对话里记下
    learned = "learned"  # 从用户的修改/反馈中学到（经用户确认）
    benchmark = "benchmark"  # 复刻对标账号时按对方打法生成


class TopicStatus(str, Enum):
    new = "new"
    used = "used"
    dismissed = "dismissed"


class DraftStatus(str, Enum):
    pending_review = "pending_review"  # 待审核
    approved = "approved"  # 满意，可以发
    exported = "exported"  # 已导出（视为已发）
    rejected = "rejected"  # 不要了


class ImageStatus(str, Enum):
    pending = "pending"
    running = "running"
    done = "done"
    failed = "failed"
    skipped = "skipped"  # 未配置配图服务


class JobKind(str, Enum):
    write_draft = "write_draft"
    generate_images = "generate_images"
    clone_creator = "clone_creator"  # 拆解对标账号并生成复刻方案
    find_benchmarks = "find_benchmarks"  # 按主题找同领域的对标候选
    revise_draft = "revise_draft"  # 按质检意见再改一轮草稿
    learn_visual = "learn_visual"  # 看对标账号（或给的笔记）的图，学账号配图模板


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class Trigger(str, Enum):
    manual = "manual"
    chat = "chat"
    auto = "auto"


class ChatRole(str, Enum):
    user = "user"
    assistant = "assistant"
    tool = "tool"  # 管家执行过的操作，作为记忆保留


# ─── 表 ──────────────────────────────────────────────────────────────────────


class User(SQLModel, table=True):
    id: str = Field(default_factory=_id, primary_key=True)
    name: str = "本地用户"
    # 在线版登录用；本地版的默认用户这些都为空
    username: str | None = Field(default=None, index=True, unique=True)
    password_hash: str = ""
    is_admin: bool = False
    disabled: bool = False
    token_version: int = 0  # 改密码 / 停用时 +1，旧的登录全部失效
    last_login_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)


class Account(SQLModel, table=True):
    id: str = Field(default_factory=_id, primary_key=True)
    user_id: str = Field(index=True, foreign_key="user.id")
    name: str
    # 定位
    theme: str = ""
    audience: str = ""
    content_style: str = ""
    image_style: str = ""
    topic_type: str = ""
    keywords: list[str] = json_col()
    # 多个对标账号合成后的方案：借鉴了谁的什么、栏目、起号建议、同步了哪些东西
    bench_plan: dict = json_obj_col()
    # 最近一次「帮我找同领域的号」的结果：{theme, prefer, candidates, notes, at}，对标页按小红书的样子展示
    bench_candidates: dict = json_obj_col()
    # 账号配图模板（看对标账号的图学出来的）：{spec, pages: [{type, desc, when, examples: [_refs/…]}], tips, source, at}
    # 有模板时每篇配图都照它，整个账号看起来是一套
    visual: dict = json_obj_col()
    # 小媒的长期记忆：早的聊天滚动压成要点 {summary, upto(压到哪条消息的时间), at}，最近的聊天原样给模型
    chat_memory: dict = json_obj_col()
    # 配图默认怎么出：ai 整张 AI 画 / mixed AI 画面 + 代码排字 / card 代码排版卡片 / photo 网上找图 + 代码排字 / auto 每张自己挑
    image_mode: str = "ai"
    # 自动模式
    auto_enabled: bool = False
    auto_frequency: AutoFrequency = AutoFrequency.daily
    last_auto_run_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Rule(SQLModel, table=True):
    id: str = Field(default_factory=_id, primary_key=True)
    user_id: str = Field(index=True, foreign_key="user.id")
    account_id: str = Field(index=True, foreign_key="account.id")
    text: str
    source: RuleSource = RuleSource.user
    active: bool = True
    created_at: datetime = Field(default_factory=utcnow)


class Note(SQLModel, table=True):
    """运营笔记：管家调研后存下的结论（对标账号分析、爆款规律等），写稿和出选题时作为参考。"""

    id: str = Field(default_factory=_id, primary_key=True)
    user_id: str = Field(index=True, foreign_key="user.id")
    account_id: str = Field(index=True, foreign_key="account.id")
    title: str
    content: str
    created_at: datetime = Field(default_factory=utcnow)


class BenchmarkStatus(str, Enum):
    analyzing = "analyzing"
    ready = "ready"
    failed = "failed"


class Benchmark(SQLModel, table=True):
    """对标账号：一个博主一条，存拆解出来的打法（playbook）和爆款样本。一个账号最多同时对标 3 个，合成方案存在 Account.bench_plan。"""

    id: str = Field(default_factory=_id, primary_key=True)
    user_id: str = Field(index=True, foreign_key="user.id")
    account_id: str = Field(index=True, foreign_key="account.id")
    platform: str = "xiaohongshu"
    target: str = ""  # 用户输入的链接 / 名字
    theme: str = ""  # 用户想换成的主题
    creator_name: str = ""
    creator_url: str = ""
    creator_info: dict = json_obj_col()  # 粉丝、获赞、简介、更新频率等
    status: BenchmarkStatus = BenchmarkStatus.analyzing
    playbook: dict = json_obj_col()  # 拆解结果：人设、栏目、标题公式、结构、视觉…
    plan: dict = json_obj_col()  # 换主题后的方案：定位、规则、起号建议
    samples: list[dict] = json_col()  # 爆款样本（标题、互动、正文摘要、标签、热评）
    error: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Topic(SQLModel, table=True):
    id: str = Field(default_factory=_id, primary_key=True)
    user_id: str = Field(index=True, foreign_key="user.id")
    account_id: str = Field(index=True, foreign_key="account.id")
    title: str
    angle: str = ""
    reason: str = ""
    source: str = "ai"  # weibo / baidu / bilibili / douyin / ai / user
    source_url: str = ""
    reference: dict = json_obj_col()  # 复刻选题对应的原爆款（标题、互动、正文摘要），写稿时学结构
    status: TopicStatus = TopicStatus.new
    created_at: datetime = Field(default_factory=utcnow)


class Draft(SQLModel, table=True):
    id: str = Field(default_factory=_id, primary_key=True)
    user_id: str = Field(index=True, foreign_key="user.id")
    account_id: str = Field(index=True, foreign_key="account.id")
    topic_id: str | None = Field(default=None, foreign_key="topic.id")
    title: str
    body: str
    tags: list[str] = json_col()
    # 生成原稿快照：用户修改后用来对比学习
    original_title: str = ""
    original_body: str = ""
    status: DraftStatus = DraftStatus.pending_review
    trigger: Trigger = Trigger.manual
    score: float | None = None
    evaluation: dict = json_obj_col()  # 各维度分数、问题、建议
    check_issues: list[str] = json_col()  # 代码硬检查没通过的项
    attempts: int = 1
    needs_attention: bool = False  # 质检失败/有硬伤时提醒用户重点看
    reference: dict = json_obj_col()  # 这篇照着哪些帖子写：主参考帖（配图照它，含原图缓存）+ extra（只给文案参考）
    image_spec: str = ""  # 这套配图统一的视觉规范（重出某张时沿用）
    image_mold: str = ""  # 配图照什么做的版式：post = 主参考帖原图一张对一张；template = 账号配图模板的页型样例；空 = 没有模板
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class DraftImage(SQLModel, table=True):
    id: str = Field(default_factory=_id, primary_key=True)
    draft_id: str = Field(index=True, foreign_key="draft.id")
    idx: int
    prompt: str  # 中文画面描述（来自写稿）
    expanded_prompt: str = ""  # 扩写后的生图提示词
    status: ImageStatus = ImageStatus.pending
    path: str = ""  # 相对 data/images 的路径
    ref_path: str = ""  # 照着原帖哪张图出的（相对 data/images，_refs/ 下的缓存）
    page_type: str = ""  # 账号配图模板里的哪种页（封面/清单页/对比页…）
    review: dict = json_obj_col()  # 出图后看图自检：{ok, problems, fix, redone, at}
    mode: str = ""  # 用户给这张指定的做法（ai / ai_text / card / photo），空 = 跟账号设定走
    made_by: str = ""  # 这张实际是怎么做的：ai / ai_text（AI 画面 + 代码排字）/ card（代码排版）/ photo（网上找图 + 代码排字）
    layout: dict = json_obj_col()  # 代码排的字：{kind, title, subtitle, items, left, right, tag, highlight, position, palette}
    source: dict = json_obj_col()  # 底图从哪来：{base: 底图本地路径, url, link, site, title, query}（网上找的图记出处）
    error: str = ""
    updated_at: datetime = Field(default_factory=utcnow)


class Feedback(SQLModel, table=True):
    id: str = Field(default_factory=_id, primary_key=True)
    user_id: str = Field(index=True, foreign_key="user.id")
    draft_id: str = Field(index=True, foreign_key="draft.id")
    rating: str  # good / bad
    comment: str = ""
    created_at: datetime = Field(default_factory=utcnow)


class ChatMessage(SQLModel, table=True):
    id: str = Field(default_factory=_id, primary_key=True)
    user_id: str = Field(index=True, foreign_key="user.id")
    account_id: str = Field(index=True, foreign_key="account.id")
    role: ChatRole
    content: str
    tool_name: str = ""
    payload: dict = json_obj_col()
    created_at: datetime = Field(default_factory=utcnow, index=True)


class Job(SQLModel, table=True):
    id: str = Field(default_factory=_id, primary_key=True)
    user_id: str = Field(index=True, foreign_key="user.id")
    account_id: str | None = Field(default=None, index=True, foreign_key="account.id")
    kind: JobKind
    payload: dict = json_obj_col()
    status: JobStatus = Field(default=JobStatus.queued, index=True)
    events: list[dict] = json_col()  # 进度事件，前端轮询展示
    result: dict = json_obj_col()
    error: str = ""
    created_at: datetime = Field(default_factory=utcnow, index=True)
    started_at: datetime | None = None
    finished_at: datetime | None = None
