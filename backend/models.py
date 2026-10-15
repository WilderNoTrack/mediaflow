import uuid
from datetime import datetime
from enum import Enum as PyEnum
from sqlalchemy import Column, String, Text, DateTime, Enum, ForeignKey, JSON, Boolean

from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class UserStatus(PyEnum):
    active = "active"
    banned = "banned"


class SubscriptionPlan(PyEnum):
    basic = "basic"
    pro = "pro"
    enterprise = "enterprise"


class SubscriptionStatus(PyEnum):
    trial = "trial"
    active = "active"
    expired = "expired"


class AccountStatus(PyEnum):
    active = "active"
    error = "error"


class ContentStatus(PyEnum):
    draft = "draft"
    pending = "pending"
    published = "published"
    failed = "failed"


class PublishStatus(PyEnum):
    success = "success"
    failed = "failed"


class MessageRole(PyEnum):
    user = "user"
    assistant = "assistant"


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    phone = Column(String(20), unique=True, nullable=True)
    wechat_id = Column(String(100), unique=True, nullable=True)
    email = Column(String(255), unique=True, nullable=True)
    password_hash = Column(String(255), nullable=True)
    nickname = Column(String(100), nullable=True)
    avatar_url = Column(String(255), nullable=True)
    bio = Column(Text, nullable=True)
    language = Column(String(10), default="zh-CN")
    timezone = Column(String(50), default="Asia/Shanghai")
    notification_settings = Column(JSON, nullable=True)
    appearance_settings = Column(JSON, nullable=True)
    last_login_at = Column(DateTime, nullable=True)
    status = Column(Enum(UserStatus), default=UserStatus.active)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    subscriptions = relationship("Subscription", back_populates="user")
    xiaohongshu_accounts = relationship("XiaohongshuAccount", back_populates="user")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    plan = Column(Enum(SubscriptionPlan), default=SubscriptionPlan.basic)
    status = Column(Enum(SubscriptionStatus), default=SubscriptionStatus.trial)
    trial_start = Column(DateTime, nullable=True)
    trial_end = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    auto_renew = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="subscriptions")


class TopicStatus(PyEnum):
    suggested = "suggested"
    selected = "selected"
    used = "used"
    skipped = "skipped"


class XiaohongshuAccount(Base):
    __tablename__ = "xiaohongshu_accounts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    username = Column(String(100), nullable=False)
    xhs_user_id = Column(String(100), nullable=True)
    nickname = Column(String(100), nullable=True)
    avatar_url = Column(String(255), nullable=True)
    fans_count = Column(String(50), nullable=True)
    likes_count = Column(String(50), nullable=True)
    cookies = Column(Text, nullable=True)
    cookies_encrypted = Column(Boolean, default=False)
    status = Column(Enum(AccountStatus), default=AccountStatus.active)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 账号孵化配置字段
    theme = Column(String(100), nullable=True)            # 账号主题，如"精致下午茶"
    target_audience = Column(String(200), nullable=True)  # 目标受众
    content_style = Column(Text, nullable=True)           # 内容风格描述
    image_style = Column(Text, nullable=True)             # 配图风格，如"封面效果图+过程图+整体展示"
    topic_type = Column(Text, nullable=True)              # 选题类型，如"西餐菜品"，用来生成具体选题词
    keywords = Column(JSON, nullable=True)                # 具体选题词，如["芝士焗虾","意式烩饭"]
    requirements = Column(JSON, nullable=True)            # 文案要求列表

    # 自动运营字段（Agent 自动化）
    auto_enabled = Column(Boolean, default=False)         # 是否开启自动运营
    auto_frequency = Column(String(20), default="daily")  # daily / every_2_days / weekly
    auto_count = Column(String(5), default="1")           # 每次自动产出几篇
    last_auto_run = Column(DateTime, nullable=True)       # 上次自动运行时间

    user = relationship("User", back_populates="xiaohongshu_accounts")
    publish_logs = relationship("PublishLog", back_populates="account")
    topics = relationship("Topic", back_populates="account")
    account_contents = relationship("Content", back_populates="account",
                                    foreign_keys="Content.account_id")
    account_conversations = relationship("AccountConversation", back_populates="account")


class Topic(Base):
    """选题库：每个账号独立的选题记录"""
    __tablename__ = "topics"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    account_id = Column(String(36), ForeignKey("xiaohongshu_accounts.id"), nullable=False, index=True)
    title = Column(String(255), nullable=False)          # 选题标题
    angle = Column(Text, nullable=True)                   # 内容切入点
    source = Column(String(50), nullable=True)            # xiaohongshu / douyin / weibo / baidu / ai
    source_url = Column(String(500), nullable=True)
    hot_score = Column(String(10), nullable=True)         # 热度评级 1-5
    status = Column(Enum(TopicStatus), default=TopicStatus.suggested)
    created_at = Column(DateTime, default=datetime.utcnow)

    account = relationship("XiaohongshuAccount", back_populates="topics")


class AccountConversation(Base):
    """每个账号的独立配置对话记录"""
    __tablename__ = "account_conversations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    account_id = Column(String(36), ForeignKey("xiaohongshu_accounts.id"), nullable=False, index=True)
    role = Column(Enum(MessageRole), nullable=False)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    account = relationship("XiaohongshuAccount", back_populates="account_conversations")


class XiaohongshuAccountBinding(Base):
    __tablename__ = "xiaohongshu_account_bindings"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    mcp_account_id = Column(String(8), nullable=False, unique=True)
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Content(Base):
    __tablename__ = "contents"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    # 直接归属用户；account_id 为空时（未挂到具体账号的独立草稿）也能确定所有者
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    account_id = Column(String(36), ForeignKey("xiaohongshu_accounts.id"), nullable=True, index=True)
    topic_id = Column(String(36), ForeignKey("topics.id"), nullable=True)
    title = Column(String(255), nullable=True)
    content = Column(Text, nullable=True)
    images = Column(JSON, nullable=True)
    image_prompts = Column(JSON, nullable=True)   # 每张图的中文拍摄说明
    tags = Column(JSON, nullable=True)
    status = Column(Enum(ContentStatus), default=ContentStatus.draft)
    # 配图生成状态：none / pending / done / partial / failed
    # 后台生图是异步的，没有这个字段时失败完全静默，用户只看到永远的占位图
    image_status = Column(String(20), default="none")
    quality_score = Column(String(5), nullable=True)   # Agent 质检评分 1-10
    needs_review = Column(Boolean, default=False)      # 质检未真正执行（服务降级），需人工确认
    scheduled_at = Column(DateTime, nullable=True)
    published_at = Column(DateTime, nullable=True)
    xiaohongshu_note_id = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    account = relationship("XiaohongshuAccount", back_populates="account_contents",
                           foreign_keys=[account_id])
    publish_logs = relationship("PublishLog", back_populates="content")


class PublishLog(Base):
    __tablename__ = "publish_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    content_id = Column(String(36), ForeignKey("contents.id"), nullable=False)
    account_id = Column(String(36), ForeignKey("xiaohongshu_accounts.id"), nullable=False)
    status = Column(Enum(PublishStatus), nullable=False)
    error_message = Column(Text, nullable=True)
    xiaohongshu_note_id = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    content = relationship("Content", back_populates="publish_logs")
    account = relationship("XiaohongshuAccount", back_populates="publish_logs")


class AgentRunStatus(PyEnum):
    running = "running"
    success = "success"
    failed = "failed"


class AgentRun(Base):
    """一次 Agent 内容创作的运行记录。

    此前 Agent 跑完只在日志里留痕，事后无法复盘「这篇为什么这么差」，
    成本也完全不可见。
    """
    __tablename__ = "agent_runs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    account_id = Column(String(36), ForeignKey("xiaohongshu_accounts.id"), nullable=False, index=True)
    trigger = Column(String(20), nullable=False)        # manual / manager / auto
    status = Column(Enum(AgentRunStatus), default=AgentRunStatus.running)
    steps = Column(JSON, nullable=True)                 # [{step, tool, ok, ms}, ...]
    step_count = Column(String(5), nullable=True)
    score = Column(String(5), nullable=True)            # 最终采用内容的质检分
    content_id = Column(String(36), nullable=True)      # 产出的草稿
    token_usage = Column(JSON, nullable=True)           # {calls, prompt, completion, total}
    error = Column(Text, nullable=True)
    duration_ms = Column(String(12), nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)


class ContentConfig(Base):
    __tablename__ = "content_configs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    config_key = Column(String(100), nullable=False)
    config_value = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class EmailVerificationCode(Base):
    __tablename__ = "email_verification_codes"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), nullable=False, index=True)
    code = Column(String(10), nullable=False)
    purpose = Column(String(20), nullable=False)  # 'register' or 'reset_password'
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class PublishTaskStatus(PyEnum):
    pending = "pending"
    publishing = "publishing"
    published = "published"
    failed = "failed"


class PublishTask(Base):
    """发布任务表"""
    __tablename__ = "publish_tasks"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    content_id = Column(String(36), ForeignKey("contents.id"), nullable=True)
    platform = Column(String(50), nullable=False)  # 'xiaohongshu'
    status = Column(Enum(PublishTaskStatus), default=PublishTaskStatus.pending)
    title = Column(Text, nullable=True)
    content = Column(Text, nullable=True)
    images = Column(JSON, nullable=True)
    tags = Column(JSON, nullable=True)
    scheduled_at = Column(DateTime, nullable=True)
    published_at = Column(DateTime, nullable=True)
    platform_note_id = Column(String(100), nullable=True)
    platform_url = Column(String(255), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)