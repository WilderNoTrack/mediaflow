"""接口的请求 / 响应结构。前端类型由 OpenAPI 自动生成，保持两边一致。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from mediaflow.domain.models import (
    AutoFrequency, BenchmarkStatus, ChatRole, DraftStatus, ImageStatus, JobKind, JobStatus, RuleSource, TopicStatus, Trigger,
)


class AccountIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    theme: str = ""
    audience: str = ""


class AccountPatch(BaseModel):
    name: str | None = None
    theme: str | None = None
    audience: str | None = None
    content_style: str | None = None
    image_style: str | None = None
    image_mode: Literal["ai", "mixed", "card", "photo", "auto"] | None = None
    topic_type: str | None = None
    keywords: list[str] | None = None
    auto_enabled: bool | None = None
    auto_frequency: AutoFrequency | None = None


class RuleOut(BaseModel):
    id: str
    text: str
    source: RuleSource
    active: bool
    created_at: datetime


class NoteOut(BaseModel):
    id: str
    title: str
    content: str
    created_at: datetime


class AccountOut(BaseModel):
    id: str
    name: str
    theme: str
    audience: str
    content_style: str
    image_style: str
    image_mode: str = "ai"
    topic_type: str
    keywords: list[str]
    auto_enabled: bool
    auto_frequency: AutoFrequency
    last_auto_run_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AccountSummary(AccountOut):
    pending_review: int = 0
    total_drafts: int = 0
    writing: bool = False


class BenchmarkOut(BaseModel):
    id: str
    platform: str
    target: str
    theme: str
    creator_name: str
    creator_url: str
    creator_info: dict
    status: BenchmarkStatus
    playbook: dict
    plan: dict
    samples: list[dict]
    error: str
    created_at: datetime
    updated_at: datetime


class BenchmarkIn(BaseModel):
    targets: list[str] = Field(default=[], max_length=3, description="要对标的账号（1-3 个）：主页链接、笔记链接、名字或小红书号")
    target: str = Field("", max_length=500, description="只对标一个时也可以用这个字段")
    names: list[str] = Field(default=[], max_length=3, description="可选：和 targets 一一对应的博主名字（从候选里选时带上，拆解前就能显示）")
    theme: str = Field("", max_length=100, description="想换成的主题，留空用账号现有主题")
    platform: str = Field("xiaohongshu", description="只写了名字时去哪个平台找；给的是链接就按链接认平台（小红书/抖音/微博）")


class CandidatesIn(BaseModel):
    query: str = Field("", max_length=100, description="方向，留空用账号主题")
    prefer: str = Field("", max_length=200, description="额外要求，如「粉丝少一点」「做通勤穿搭」")
    platform: str = Field("xiaohongshu", description="在哪个平台找：xiaohongshu / douyin（只看图文）/ weibo")


class ReviseIn(BaseModel):
    note: str = Field(default="", max_length=300)


class CandidatesOut(BaseModel):
    theme: str
    candidates: list[dict]
    notes: list[str] = []


class RemoveBenchmarkOut(BaseModel):
    job: "JobOut | None" = None


class CreatorOut(BaseModel):
    name: str
    fans: str
    posts: str
    desc: str
    url: str


class AccountDetail(AccountOut):
    rules: list[RuleOut]
    notes: list[NoteOut] = []
    benchmarks: list[BenchmarkOut] = []
    bench_plan: dict = {}
    bench_candidates: dict = {}
    visual: dict = Field(default={}, description="账号配图模板：spec 整体视觉、pages 页型（type/desc/when/examples 样例图本地路径）、"
                                                 "tips、source 从哪学的、at")


class RuleIn(BaseModel):
    text: str = Field(min_length=1, max_length=300)
    source: RuleSource = RuleSource.user


class TopicOut(BaseModel):
    id: str
    title: str
    angle: str
    reason: str
    source: str
    source_url: str
    reference: dict = {}
    status: TopicStatus
    created_at: datetime


class TopicIn(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    angle: str = ""


class TopicStatusIn(BaseModel):
    status: TopicStatus


class SourceStatusOut(BaseModel):
    source: str
    label: str
    ok: bool
    count: int
    note: str
    mode: str = ""


class TopicSearchIn(BaseModel):
    direction: str = ""


class TopicSearchOut(BaseModel):
    topics: list[TopicOut]
    sources: list[SourceStatusOut]
    note: str
    skipped_duplicates: int


class ImageOut(BaseModel):
    id: str
    idx: int
    prompt: str
    status: ImageStatus
    url: str | None
    error: str
    ref_url: str | None = Field(None, description="这张照着参考帖哪张原图出的（本地缓存地址）")
    page_type: str = Field("", description="用的账号配图模板里哪种页")
    review: dict = Field(default={}, description="出图后看图自检：ok/problems/redone（重出过一次）/before（重出前的问题）")
    mode: str = Field("", description="用户给这张指定的做法，空 = 跟账号设定")
    made_by: str = Field("", description="实际怎么做的：ai / ai_text / card / photo")
    layout: dict = Field(default={}, description="代码排上去的字（能直接改）")
    source: dict = Field(default={}, description="网上找的图的出处：url / link / site / title / query；fallback = 没找到图改成了卡片")
    base_url: str | None = Field(None, description="没叠字的底图")


class DraftOut(BaseModel):
    id: str
    account_id: str
    topic_id: str | None
    title: str
    body: str
    tags: list[str]
    status: DraftStatus
    trigger: Trigger
    score: float | None
    evaluation: dict
    check_issues: list[str]
    attempts: int
    needs_attention: bool
    edited: bool
    cover_url: str | None
    images_total: int = 0
    images_done: int = 0
    images_busy: int = Field(0, description="排队中或正在出的配图张数")
    reference: dict = Field(default={}, description="这篇照着哪些帖子写：主参考帖 title/url/creator/likes/why/local(原图本地路径)，"
                                                    "配图只照它；extra 是只给文案参考的其他帖子")
    image_spec: str = Field("", description="这套配图统一的视觉规范")
    image_mold: str = Field("", description="配图版式照什么：post=主参考帖原图一张对一张，template=账号配图模板，空=都没有")
    created_at: datetime
    updated_at: datetime


class DraftDetail(DraftOut):
    original_title: str
    original_body: str
    images: list[ImageOut]


class DraftPatch(BaseModel):
    title: str | None = None
    body: str | None = None
    tags: list[str] | None = None
    status: DraftStatus | None = None


class FeedbackIn(BaseModel):
    rating: str = Field(pattern="^(good|bad)$")
    comment: str = ""


class LearnOut(BaseModel):
    rules: list[str]
    summary: str


class WriteIn(BaseModel):
    topic_id: str | None = None
    hint: str = ""
    from_chat: bool = Field(False, description="在小媒对话里点的「写这篇」：把这次写稿记进对话，进度和结果卡片留在对话里")
    image_plan: list[str] = Field(default=[], max_length=9, description="用户对每张图的要求（第 1 张、第 2 张…），写稿时照这个出配图描述")
    reference_url: str = Field("", max_length=3000, description="照着这些小红书笔记写（可以多个链接/分享文字，第一篇图文笔记当配图模板；不填就自动挑）")


class CompareSide(BaseModel):
    title: str = Field("", max_length=12)
    items: list[str] = Field(default=[], max_length=6)


class ImageLayout(BaseModel):
    """代码排上去的字。kind：cover 封面大字 / list 清单 / steps 步骤 / compare 对比 / quote 金句"""
    kind: Literal["cover", "list", "steps", "compare", "quote"] | None = None
    title: str | None = Field(None, max_length=90)
    subtitle: str | None = Field(None, max_length=90)
    tag: str | None = Field(None, max_length=14)
    highlight: str | None = Field(None, max_length=30)
    items: list[str] | None = Field(None, max_length=8)
    left: CompareSide | None = None
    right: CompareSide | None = None
    position: Literal["top", "center", "bottom"] | None = None
    palette: str | None = Field(None, max_length=20)


class ImageOp(BaseModel):
    op: Literal["update", "add", "remove", "move", "redo", "mode", "text"]
    no: int | None = Field(None, description="第几张（按改之前的顺序，从 1 开始）")
    after: int | None = Field(None, description="add：加在第几张后面，0 = 放最前，不填放最后")
    to: int | None = Field(None, description="move：挪到第几张")
    description: str = Field("", max_length=500, description="update/add：这张图的中文画面描述")
    mode: Literal["", "ai", "ai_text", "card", "photo"] | None = Field(
        None, description="mode/add：这张怎么做 ai 整张 AI 画 / ai_text AI 画面 + 代码排字 / card 排版卡片 / photo 网上找图 + 排字，空 = 跟账号设定")
    layout: ImageLayout | None = Field(None, description="text：改后的字（只传要改的），马上重排、不重新生图")


class ImageEditIn(BaseModel):
    ops: list[ImageOp] = Field(min_length=1, max_length=20)
    regenerate: bool = Field(True, description="改完马上把改过的、新加的出图")


class VisualLearnIn(BaseModel):
    links: str = Field("", max_length=3000, description="照着这几篇笔记学（链接或整段分享文字，可多个）；不填就看对标账号的爆款图")


class VisualPage(BaseModel):
    type: str = Field(min_length=1, max_length=12)
    desc: str = Field("", max_length=200)
    when: str = Field("", max_length=80)
    examples: list[str] = Field(default=[], description="样例图本地路径（_refs/…），不填按页型名字沿用原来的")
    from_: str = Field("", alias="from", description="改名时原来的页型名字（沿用它的样例图）")


class VisualPatch(BaseModel):
    spec: str | None = Field(None, max_length=500)
    pages: list[VisualPage] | None = Field(None, max_length=8)


class ReferenceIn(BaseModel):
    url: str = Field(max_length=1000, description="配图照着的那篇小红书图文笔记链接（也支持 xhslink 短链、整段分享文字）")


class JobOut(BaseModel):
    id: str
    account_id: str | None
    kind: JobKind
    status: JobStatus
    payload: dict
    events: list[dict]
    result: dict
    error: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class ChatIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    draft_id: str | None = Field(None, description="用户正在看的草稿（在草稿页跟小媒聊时带上，「第二张」就指这篇的第二张图）")


class ChatMessageOut(BaseModel):
    id: str
    role: ChatRole
    content: str
    tool_name: str
    payload: dict
    created_at: datetime


class SystemStatus(BaseModel):
    version: str
    llm_configured: bool
    image_configured: bool
    vision_available: bool = Field(False, description="能看图（学配图模板、出图自检）")
    weibo_cookie_configured: bool
    data_dir: str


RemoveBenchmarkOut.model_rebuild()
