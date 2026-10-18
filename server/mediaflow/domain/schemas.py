"""接口的请求 / 响应结构。前端类型由 OpenAPI 自动生成，保持两边一致。"""

from __future__ import annotations

from datetime import datetime

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
    target: str = Field(min_length=1, max_length=500, description="对标账号：主页链接、笔记链接、名字或小红书号")
    theme: str = Field("", max_length=100, description="想换成的主题，留空用账号现有主题")
    platform: str = "xiaohongshu"


class CreatorOut(BaseModel):
    name: str
    fans: str
    posts: str
    desc: str
    url: str


class AccountDetail(AccountOut):
    rules: list[RuleOut]
    notes: list[NoteOut] = []
    benchmark: BenchmarkOut | None = None


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
    weibo_cookie_configured: bool
    data_dir: str
