# Router 实现模板

**说明**: 本文档包含所有 7 个 Router 模块的完整实现模板
**使用方法**: 复制对应模块的代码到 `backend/routers/` 目录
**来源**: 基于 `main.py` 的现有代码拆分

---

## 📋 目录

1. [auth.py - 认证模块](#1-authpy---认证模块)
2. [users.py - 用户管理](#2-userspy---用户管理)
3. [lobsters.py - AI员工管理](#3-lobsterspy---ai员工管理)
4. [chat.py - 对话系统](#4-chatpy---对话系统)
5. [contents.py - 内容管理](#5-contentspy---内容管理)
6. [publish.py - 发布系统](#6-publishpy---发布系统)
7. [config.py - 配置管理](#7-configpy---配置管理)
8. [dependencies.py - 共享依赖](#8-dependenciespy---共享依赖)
9. [routers/__init__.py - 统一注册](#9-routersinitpy---统一注册)

---

## 1. auth.py - 认证模块

**文件**: `backend/routers/auth.py`
**负责人**: Person A
**端点**: 4 个

```python
from datetime import datetime, timedelta
from typing import Optional
import uuid
from uuid import UUID
import hashlib
import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database import get_db
from models import User, EmailVerificationCode, Subscription, Lobster
from dependencies import (
    hash_password,
    create_token,
    generate_verification_code,
    send_verification_email
)

router = APIRouter(prefix="/api/auth", tags=["认证"])

# ============== Pydantic Models ==============

class LoginRequest(BaseModel):
    phone: Optional[str] = None
    email: Optional[str] = None
    password: str


class RegisterRequest(BaseModel):
    phone: Optional[str] = None
    email: Optional[str] = None
    password: str
    nickname: Optional[str] = None
    code: Optional[str] = None  # Verification code for registration


class SendCodeRequest(BaseModel):
    email: str
    purpose: str  # 'register' or 'reset_password'


class ResetPasswordRequest(BaseModel):
    email: str
    code: str
    new_password: str


# ============== Endpoints ==============

@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    """用户注册
    
    Args:
        req: 注册请求，包含 phone/email/password/nickname/code
        
    Returns:
        Token 响应，包含 access_token 和用户信息
        
    Raises:
        400: 缺少必填字段、验证码无效、用户已存在
    """
    # 验证必填字段
    if not req.phone and not req.email:
        raise HTTPException(status_code=400, detail="Phone or email required")
    
    # 验证邮箱验证码（如果使用邮箱注册）
    if req.email and req.code:
        now = datetime.utcnow()
        verification = db.query(EmailVerificationCode).filter(
            EmailVerificationCode.email == req.email,
            EmailVerificationCode.code == req.code,
            EmailVerificationCode.purpose == "register",
            EmailVerificationCode.used == False,
            EmailVerificationCode.expires_at > now
        ).first()
        
        if not verification:
            raise HTTPException(status_code=400, detail="Invalid or expired verification code")
        
        # 标记验证码已使用
        verification.used = True
        db.commit()
    elif req.email and not req.code:
        raise HTTPException(status_code=400, detail="Verification code is required for email registration")
    
    # 检查用户是否已存在
    existing = None
    if req.phone:
        existing = db.query(User).filter(User.phone == req.phone).first()
    if not existing and req.email:
        existing = db.query(User).filter(User.email == req.email).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="User already exists")
    
    # 创建用户
    user = User(
        id=str(uuid.uuid4()),
        phone=req.phone,
        email=req.email,
        password_hash=hash_password(req.password),
        nickname=req.nickname
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    
    # 创建 7 天试用期订阅
    trial_end = datetime.utcnow() + timedelta(days=7)
    subscription = Subscription(
        id=str(uuid.uuid4()),
        user_id=user.id,
        plan="basic",
        status="trial",
        trial_start=datetime.utcnow(),
        trial_end=trial_end
    )
    db.add(subscription)
    
    # 创建默认 AI 员工"阿龙"
    lobster = Lobster(
        id=str(uuid.uuid4()),
        user_id=user.id,
        name="阿龙",
        domain="general"
    )
    db.add(lobster)
    db.commit()
    
    # 生成并返回 Token
    token = create_token(user.id)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": str(user.id),
            "phone": user.phone,
            "email": user.email,
            "nickname": user.nickname
        }
    }


@router.post("/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    """用户登录
    
    Args:
        req: 登录请求，包含 phone/email/password
        
    Returns:
        Token 响应，包含 access_token 和用户信息
        
    Raises:
        400: 缺少 phone 或 email
        401: 凭据无效
    """
    if not req.phone and not req.email:
        raise HTTPException(status_code=400, detail="Phone or email required")
    
    user = db.query(User).filter(
        (User.phone == req.phone) | (User.email == req.email)
    ).first()
    
    if not user or user.password_hash != hash_password(req.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    token = create_token(user.id)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": str(user.id),
            "phone": user.phone,
            "email": user.email,
            "nickname": user.nickname
        }
    }


@router.post("/send-code")
async def send_code(req: SendCodeRequest, db: Session = Depends(get_db)):
    """发送验证码到邮箱
    
    Args:
        req: 发送验证码请求，包含 email 和 purpose
        
    Returns:
        验证码发送成功消息和有效期
        
    Raises:
        400: purpose 无效或邮箱已注册
        429: 频率限制
        500: 邮件发送失败
    """
    # 验证 purpose
    if req.purpose not in ["register", "reset_password"]:
        raise HTTPException(
            status_code=400,
            detail="Invalid purpose. Must be 'register' or 'reset_password'"
        )
    
    # 检查邮箱是否已注册（仅针对注册用途）
    if req.purpose == "register":
        existing = db.query(User).filter(User.email == req.email).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")
    
    # 检查频率限制：同一邮箱 1 秒内只能发送一次
    now = datetime.utcnow()
    recent_code = db.query(EmailVerificationCode).filter(
        EmailVerificationCode.email == req.email,
        EmailVerificationCode.purpose == req.purpose,
        EmailVerificationCode.created_at > now - timedelta(seconds=1)
    ).first()
    
    if recent_code:
        wait_time = 1 - int((now - recent_code.created_at).total_seconds())
        raise HTTPException(
            status_code=429,
            detail=f"Please wait {wait_time} seconds before requesting another code"
        )
    
    # 生成验证码
    code = generate_verification_code()
    expires_at = now + timedelta(minutes=5)
    
    # 保存验证码
    verification = EmailVerificationCode(
        id=str(uuid.uuid4()),
        email=req.email,
        code=code,
        purpose=req.purpose,
        expires_at=expires_at
    )
    db.add(verification)
    db.commit()
    
    # 发送邮件
    success = await send_verification_email(req.email, code, req.purpose)
    
    if not success:
        # 邮件发送失败，回滚验证码
        db.delete(verification)
        db.commit()
        raise HTTPException(status_code=500, detail="Failed to send verification email")
    
    return {
        "message": "Verification code sent successfully",
        "expires_in": 300  # 5 分钟
    }


@router.post("/reset-password")
async def reset_password(req: ResetPasswordRequest, db: Session = Depends(get_db)):
    """重置密码
    
    Args:
        req: 重置密码请求，包含 email/code/new_password
        
    Returns:
        密码重置成功消息
        
    Raises:
        400: 验证码无效或过期
        404: 用户不存在
    """
    now = datetime.utcnow()
    
    # 验证验证码
    verification = db.query(EmailVerificationCode).filter(
        EmailVerificationCode.email == req.email,
        EmailVerificationCode.code == req.code,
        EmailVerificationCode.purpose == "reset_password",
        EmailVerificationCode.used == False,
        EmailVerificationCode.expires_at > now
    ).first()
    
    if not verification:
        raise HTTPException(status_code=400, detail="Invalid or expired verification code")
    
    # 查找用户
    user = db.query(User).filter(User.email == req.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # 更新密码
    user.password_hash = hash_password(req.new_password)
    user.updated_at = now
    
    # 标记验证码已使用
    verification.used = True
    
    db.commit()
    
    return {"message": "Password reset successfully"}
```

---

## 2. users.py - 用户管理

**文件**: `backend/routers/users.py`
**负责人**: Person A
**端点**: 2 个

```python
from datetime import datetime
from typing import Optional
from collections import Counter
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import (
    User, Subscription, Lobster, XiaohongshuAccount,
    UserPreference, ConversationHistory, AccountStatus
)
from dependencies import get_current_user

router = APIRouter(prefix="/api/user", tags=["用户管理"])


@router.get("/profile")
def get_profile(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取用户资料
    
    Returns:
        用户资料，包括订阅、AI员工、小红书账号信息
    """
    # 查询订阅
    subscription = db.query(Subscription).filter(Subscription.user_id == user.id).first()
    
    # 查询 AI 员工
    lobster = db.query(Lobster).filter(Lobster.user_id == user.id).first()
    
    # 查询小红书账号
    xiaohongshu = db.query(XiaohongshuAccount).filter(
        XiaohongshuAccount.user_id == user.id,
        XiaohongshuAccount.status == AccountStatus.active
    ).first()
    
    return {
        "id": str(user.id),
        "phone": user.phone,
        "email": user.email,
        "nickname": user.nickname,
        "created_at": user.created_at.isoformat(),
        "subscription": {
            "plan": subscription.plan.value if subscription else "basic",
            "status": subscription.status.value if subscription else "trial",
            "trial_end": subscription.trial_end.isoformat() if subscription and subscription.trial_end else None,
            "expires_at": subscription.expires_at.isoformat() if subscription and subscription.expires_at else None
        } if subscription else None,
        "lobster": {
            "id": str(lobster.id),
            "name": lobster.name,
            "domain": lobster.domain,
            "status": lobster.status.value
        } if lobster else None,
        "xiaohongshu_account": {
            "id": str(xiaohongshu.id),
            "username": xiaohongshu.username,
            "status": xiaohongshu.status.value
        } if xiaohongshu else None
    }


@router.post("/preferences/learn")
def learn_preferences(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """分析对话历史并学习用户偏好
    
    Returns:
        学习到的偏好信息
    """
    lobster = db.query(Lobster).filter(Lobster.user_id == user.id).first()
    if not lobster:
        raise HTTPException(status_code=400, detail="No lobster found")
    
    # 获取最近的对话历史
    conversations = db.query(ConversationHistory).filter(
        ConversationHistory.lobster_id == lobster.id,
        ConversationHistory.extracted_config.isnot(None)
    ).order_by(ConversationHistory.created_at.desc()).limit(20).all()
    
    if not conversations:
        return {"message": "No conversation history to analyze", "learned": False}
    
    # 聚合偏好
    domains = []
    styles = []
    frequencies = []
    image_sources = []
    all_tags = []
    
    for conv in conversations:
        config = conv.extracted_config
        if not config:
            continue
        
        if config.get("domain"):
            domains.append(config["domain"])
        if config.get("content_style"):
            styles.append(config["content_style"])
        if config.get("publish_frequency"):
            frequencies.append(config["publish_frequency"])
        if config.get("image_source"):
            image_sources.append(config["image_source"])
        if config.get("tags"):
            all_tags.extend(config["tags"])
    
    # 获取或创建偏好
    preference = db.query(UserPreference).filter(UserPreference.lobster_id == lobster.id).first()
    
    learned_preferences = {}
    
    # 最常见的领域
    if domains:
        most_common_domain = Counter(domains).most_common(1)[0][0]
        learned_preferences["domain"] = most_common_domain
        if preference:
            preference.content_source = {"domain": most_common_domain}
        else:
            preference = UserPreference(
                id=str(uuid.uuid4()),
                lobster_id=lobster.id,
                content_source={"domain": most_common_domain}
            )
            db.add(preference)
    
    # 最常见的风格
    if styles:
        most_common_style = Counter(styles).most_common(1)[0][0]
        learned_preferences["content_style"] = most_common_style
        if preference:
            preference.content_style = most_common_style
    
    # 最常见的频率
    if frequencies:
        most_common_freq = Counter(frequencies).most_common(1)[0][0]
        learned_preferences["publish_frequency"] = most_common_freq
        if preference:
            preference.publish_frequency = most_common_freq
    
    # 最常见的图片来源
    if image_sources:
        most_common_image = Counter(image_sources).most_common(1)[0][0]
        learned_preferences["image_source"] = most_common_image
        if preference:
            preference.image_source = most_common_image
    
    # 所有唯一标签
    if all_tags:
        unique_tags = list(set(all_tags))
        learned_preferences["tags"] = unique_tags
        if preference:
            preference.tags = unique_tags
    
    if preference:
        preference.learned_at = datetime.utcnow()
    
    db.commit()
    
    return {
        "message": "Preferences learned successfully",
        "learned": True,
        "preferences": learned_preferences,
        "conversations_analyzed": len(conversations)
    }
```

---

## 3. lobsters.py - AI员工管理

**文件**: `backend/routers/lobsters.py`
**负责人**: Person A
**端点**: 2 个

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Lobster, UserPreference, LobsterStatus
from dependencies import get_current_user

router = APIRouter(prefix="/api/lobsters", tags=["AI员工"])


@router.post("/create-or-update")
def create_or_update_lobster(
    request: dict,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """创建或更新 AI 员工
    
    Args:
        request: AI员工配置，包含 name/domain/status
        
    Returns:
        创建或更新成功消息和AI员工信息
    """
    name = request.get("name")
    domain = request.get("domain")
    status = request.get("status")
    
    lobster = db.query(Lobster).filter(Lobster.user_id == user.id).first()
    
    if lobster:
        # 更新现有AI员工
        if name is not None:
            lobster.name = name
        if domain is not None:
            lobster.domain = domain
        if status is not None:
            lobster.status = LobsterStatus(status)
    else:
        # 创建新AI员工
        lobster = Lobster(
            id=str(uuid.uuid4()),
            user_id=user.id,
            name=name or "阿龙",
            domain=domain or "general",
            status=LobsterStatus(status) if status else LobsterStatus.running
        )
        db.add(lobster)
    
    db.commit()
    db.refresh(lobster)
    
    return {
        "message": "Lobster created/updated successfully",
        "lobster": {
            "id": str(lobster.id),
            "name": lobster.name,
            "domain": lobster.domain,
            "status": lobster.status.value
        }
    }


@router.get("/me")
def get_lobster(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取用户的 AI 员工详情
    
    Returns:
        AI员工信息，包括偏好设置
    """
    lobster = db.query(Lobster).filter(Lobster.user_id == user.id).first()
    
    if not lobster:
        raise HTTPException(status_code=404, detail="Lobster not found")
    
    # 查询偏好
    preference = db.query(UserPreference).filter(
        UserPreference.lobster_id == lobster.id
    ).first()
    
    return {
        "id": str(lobster.id),
        "name": lobster.name,
        "domain": lobster.domain,
        "status": lobster.status.value,
        "created_at": lobster.created_at.isoformat(),
        "preferences": {
            "content_source": preference.content_source,
            "image_source": preference.image_source,
            "publish_frequency": preference.publish_frequency,
            "publish_time": preference.publish_time,
            "content_style": preference.content_style,
            "tags": preference.tags
        } if preference else None
    }
```

---

## 4. chat.py - 对话系统

**文件**: `backend/routers/chat.py`
**负责人**: Person B
**端点**: 3 个

```python
from datetime import datetime
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Lobster, ConversationHistory, UserPreference, MessageRole
from dependencies import get_current_user, extract_config_with_ai, get_ai_response

router = APIRouter(prefix="/api/chat", tags=["对话"])


@router.post("/config")
async def chat_config(
    request: dict,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """对话式配置：从用户消息中提取配置
    
    Args:
        request: 包含用户消息
        
    Returns:
        AI 响应和提取的配置
    """
    message = request.get("message", "")
    
    # 使用 AI 提取配置
    extracted_config = await extract_config_with_ai(message)
    
    # 获取 AI 员工
    lobster = db.query(Lobster).filter(Lobster.user_id == user.id).first()
    if not lobster:
        raise HTTPException(status_code=400, detail="No lobster found")
    
    # 保存用户消息到对话历史
    conversation = ConversationHistory(
        id=str(uuid.uuid4()),
        lobster_id=lobster.id,
        role=MessageRole.user,
        message=message,
        intent=extracted_config.get("domain"),
        extracted_config=extracted_config
    )
    db.add(conversation)
    
    # 生成 AI 响应
    ai_response = get_ai_response(message, extracted_config)
    
    # 保存 AI 响应到对话历史
    ai_conversation = ConversationHistory(
        id=str(uuid.uuid4()),
        lobster_id=lobster.id,
        role=MessageRole.assistant,
        message=ai_response,
        intent=extracted_config.get("domain"),
        extracted_config=extracted_config
    )
    db.add(ai_conversation)
    
    # 保存提取的配置到用户偏好
    if extracted_config:
        preference = db.query(UserPreference).filter(
            UserPreference.lobster_id == lobster.id
        ).first()
        
        if preference:
            # 更新现有偏好
            if "domain" in extracted_config:
                preference.content_source = {"domain": extracted_config["domain"]}
            if "content_style" in extracted_config:
                preference.content_style = extracted_config["content_style"]
            if "publish_frequency" in extracted_config:
                preference.publish_frequency = extracted_config["publish_frequency"]
            if "publish_time" in extracted_config:
                preference.publish_time = extracted_config["publish_time"]
            if "image_source" in extracted_config:
                preference.image_source = extracted_config["image_source"]
            if "tags" in extracted_config:
                preference.tags = extracted_config["tags"]
            preference.learned_at = datetime.utcnow()
        else:
            # 创建新偏好
            preference = UserPreference(
                id=str(uuid.uuid4()),
                lobster_id=lobster.id,
                content_source={"domain": extracted_config.get("domain")} if extracted_config.get("domain") else None,
                content_style=extracted_config.get("content_style"),
                publish_frequency=extracted_config.get("publish_frequency"),
                publish_time=extracted_config.get("publish_time"),
                image_source=extracted_config.get("image_source", "mixed"),
                tags=extracted_config.get("tags")
            )
            db.add(preference)
    
    db.commit()
    
    return {
        "message": ai_response,
        "extracted_config": extracted_config,
        "saved": True
    }


@router.post("/history")
def save_chat_history(
    request: dict,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """保存对话历史
    
    Args:
        request: 对话消息，包含 message/role/intent/extracted_config
        
    Returns:
        保存成功消息和对话ID
    """
    message = request.get("message")
    role = request.get("role", "user")
    intent = request.get("intent")
    extracted_config = request.get("extracted_config")
    
    if not message:
        raise HTTPException(status_code=400, detail="Message is required")
    
    lobster = db.query(Lobster).filter(Lobster.user_id == user.id).first()
    if not lobster:
        raise HTTPException(status_code=400, detail="No lobster found")
    
    conversation = ConversationHistory(
        id=str(uuid.uuid4()),
        lobster_id=lobster.id,
        role=MessageRole.user if role == "user" else MessageRole.assistant,
        message=message,
        intent=intent,
        extracted_config=extracted_config
    )
    db.add(conversation)
    db.commit()
    
    return {"message": "Conversation saved", "id": conversation.id}


@router.get("/history")
def get_chat_history(
    limit: int = 50,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取对话历史
    
    Args:
        limit: 返回条数，默认 50
        
    Returns:
        对话历史列表
    """
    lobster = db.query(Lobster).filter(Lobster.user_id == user.id).first()
    if not lobster:
        return {"conversations": []}
    
    conversations = db.query(ConversationHistory).filter(
        ConversationHistory.lobster_id == lobster.id
    ).order_by(ConversationHistory.created_at.desc()).limit(limit).all()
    
    return {
        "conversations": [{
            "id": c.id,
            "role": c.role.value,
            "message": c.message,
            "intent": c.intent,
            "extracted_config": c.extracted_config,
            "created_at": c.created_at.isoformat()
        } for c in conversations]
    }
```

---

## 5. contents.py - 内容管理

**文件**: `backend/routers/contents.py`
**负责人**: Person B
**端点**: 4 个

```python
from datetime import datetime
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Lobster, Content, ContentStatus
from dependencies import get_current_user

router = APIRouter(prefix="/api/contents", tags=["内容管理"])


@router.post("", status_code=201)
def create_content(
    request: dict,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """创建内容
    
    Args:
        request: 内容数据，包含 title/content/images/tags/scheduled_at
        
    Returns:
        创建成功消息和内容信息
    """
    title = request.get("title")
    content = request.get("content")
    images = request.get("images", [])
    tags = request.get("tags", [])
    scheduled_at = request.get("scheduled_at")
    
    if not title or not content:
        raise HTTPException(status_code=400, detail="Title and content are required")
    
    lobster = db.query(Lobster).filter(Lobster.user_id == user.id).first()
    if not lobster:
        raise HTTPException(status_code=400, detail="No lobster found")
    
    content_obj = Content(
        id=str(uuid.uuid4()),
        lobster_id=lobster.id,
        title=title,
        content=content,
        images=images,
        tags=tags,
        status=ContentStatus.draft,
        scheduled_at=scheduled_at
    )
    db.add(content_obj)
    db.commit()
    db.refresh(content_obj)
    
    return {
        "message": "Content created successfully",
        "content": {
            "id": str(content_obj.id),
            "title": content_obj.title,
            "content": content_obj.content,
            "status": content_obj.status.value,
            "created_at": content_obj.created_at.isoformat()
        }
    }


@router.get("")
def get_contents(
    status: Optional[str] = None,
    limit: int = 50,
    user: User = Depends(get_current_user),
    db: Session与其他 = Depends(get_db)
):
    """获取内容列表
    
    Args:
        status: 过滤状态，可选
        limit: 返回条数，默认 50
        
    Returns:
        内容列表
    """
    lobster = db.query(Lobster).filter(Lobster.user_id == user.id).first()
    if not lobster:
        return {"contents": []}
    
    query = db.query(Content).filter(Content.lobster_id == lobster.id)
    
    if status:
        query = query.filter(Content.status == ContentStatus(status))
    
    contents = query.order_by(Content.created_at.desc()).limit(limit).all()
    
    return {
        "contents": [{
            "id": str(c.id),
            "title": c.title,
            "content": c.content,
            "images": c.images,
            "tags": c.tags,
            "status": c.status.value,
            "published_at": c.published_at.isoformat() if c.published_at else None,
            "created_at": c.created_at.isoformat()
        } for c in contents]
    }


@router.put("/{content_id}")
def update_content(
    content_id: str,
    request: dict,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """更新内容
    
    Args:
        content_id: 内容 ID
        request: 更新数据
        
    Returns:
        更新成功消息
    """
    lobster = db.query(Lobster).filter(Lobster.user_id == user.id).first()
    if not lobster:
        raise HTTPException(status_code=400, detail="No lobster found")
    
    content_obj = db.query(Content).filter(
        Content.id == content_id,
        Content.lobster_id == lobster.id
    ).first()
    
    if not content_obj:
        raise HTTPException(status_code=404, detail="Content not found")
    
    # 更新字段
    if "title" in request:
        content_obj.title = request["title"]
    if "content" in request:
        content_obj.content = request["content"]
    if "images" in request:
        content_obj.images = request["images"]
    if "tags" in request:
        content_obj.tags = request["tags"]
    if "status" in request:
        content_obj.status = ContentStatus(request["status"])
    if "scheduled_at" in request:
        content_obj.scheduled_at = request["scheduled_at"]
    
    content_obj.updated_at = datetime.utcnow()
    db.commit()
    
    return {"message": "Content updated successfully"}


@router.delete("/{content_id}")
def delete_content(
    content_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """删除内容
    
    Args:
        content_id: 内容 ID
        
    Returns:
        删除成功消息
    """
    lobster = db.query(Lobster).filter(Lobster.user_id == user.id).first()
    if not lobster:
        raise HTTPException(status_code=400, detail="No lobster found")
    
    content_obj = db.query(Content).filter(
        Content.id == content_id,
        Content.lobster_id == lobster.id
    ).first()
    
    if not content_obj:
        raise HTTPException(status_code=404, detail="Content not found")
    
    db.delete(content_obj)
    db.commit()
    
    return {"message": "Content deleted successfully"}
```

---

## 6. publish.py - 发布系统

**文件**: `backend/routers/publish.py`
**负责人**: Person B
**端点**: 2 个

```python
import uuid
import httpx
import os
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import (
    Lobster, Content, PublishLog, XiaohongshuAccount,
    AccountStatus, PublishStatus, ContentStatus
)
from dependencies import get_current_user

router = APIRouter(prefix="/api/publish", tags=["发布"])

# MCP 发布服务 URL
MCP_PUBLISH_URL = os.getenv("MCP_PUBLISH_URL", "http://localhost:18060/api/v1/publish")


@router.post("")
async def publish_content(
    request: dict,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """发布内容到小红书
    
    Args:
        request: 发布数据，包含 title/content/images
        
    Returns:
        发布成功消息和笔记 ID
    """
    title = request.get("title")
    content = request.get("content")
    images = request.get("images", [])
    
    if not title or not content:
        raise HTTPException(status_code=400, detail="Title and content are required")
    
    # 查询小红书账号
    account = db.query(XiaohongshuAccount).filter(
        XiaohongshuAccount.user_id == user.id,
        XiaohongshuAccount.status == AccountStatus.active
    ).first()
    
    if not account:
        raise HTTPException(status_code=400, detail="No Xiaohongshu account bound")
    
    # 查询 AI 员工
    lobster = db.query(Lobster).filter(Lobster.user_id == user.id).first()
    if not lobster:
        raise HTTPException(status_code=400, detail="No lobster found")
    
    try:
        # 创建内容记录
        content_obj = Content(
            id=str(uuid.uuid4()),
            lobster_id=lobster.id,
            title=title,
            content=content,
            images=images,
            status=ContentStatus.published
        )
        db.add(content_obj)
        db.commit()
        db.refresh(content_obj)
        
        # 调用 MCP API 发布
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                MCP_PUBLISH_URL,
                json={
                    "title": title,
                    "content": content,
                    "images": images or [],
                    "cookies": account.cookies
                }
            )
            
            if response.status_code != 200:
                raise HTTPException(status_code=500, detail="MCP publish failed")
            
            result = response.json()
            
            # 创建发布日志
            log = PublishLog(
                id=str(uuid.uuid4()),
                content_id=content_obj.id,
                account_id=account.id,
                status=PublishStatus.success,
                xiaohongshu_note_id=result.get("note_id")
            )
            db.add(log)
            db.commit()
            
            return {
                "status": "success",
                "note_id": result.get("note_id"),
                "content_id": content_obj.id
            }
            
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="MCP service unavailable")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/logs")
def get_publish_logs(
    limit: int = 50,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取发布日志
    
    Args:
        limit: 返回条数，默认 50
        
    Returns:
        发布日志列表
    """
    lobster = db.query(Lobster).filter(Lobster.user_id == user.id).first()
    if not lobster:
        return {"logs": []}
    
    # 查询该 lobster 的所有内容
    content_ids = [c.id for c in db.query(Content).filter(
        Content.lobster_id == lobster.id
    ).all()]
    
    if not content_ids:
        return {"logs": []}
    
    # 查询发布日志
    logs = db.query(PublishLog).filter(
        PublishLog.content_id.in_(content_ids)
    ).order_by(PublishLog.created_at.desc()).limit(limit).all()
    
    return {
        "logs": [{
            "id": log.id,
            "content_id": log.content_id,
            "status": log.status.value,
            "xiaohongshu_note_id": log.xiaohongshu_note_id,
            "error_message": log.error_message,
            "created_at": log.created_at.isoformat()
        } for log in logs]
    }
```

---

## 7. config.py - 配置管理

**文件**: `backend/routers/config.py`
**负责人**: Person A
**端点**: 2 个

```python
import uuid
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from models import ContentConfig
from dependencies import get_current_user

router = APIRouter(prefix="/api/config", tags=["配置管理"])


@router.get("")
def get_config(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取用户配置
    
    Returns:
        用户配置字典
    """
    configs = db.query(ContentConfig).filter(
        ContentConfig.user_id == user.id
    ).all()
    
    result = {}
    for config in configs:
        result[config.config_key] = config.config_value
    
    return {"configs": result}


@router.post("")
def save_config(
    request: dict,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """保存用户配置
    
    支持两种格式：
    1. 单个配置：{"config_key": "domain", "config_value": "hiphop"}
    2. 批量配置：{"domain": "hiphop", "style": "轻松搞笑", ...}
    
    Returns:
        保存成功消息
    """
    config_key = request.get("config_key")
    config_value = request.get("config_value")
    
    if config_key and config_value is not None:
        # 保存单个配置
        config = db.query(ContentConfig).filter(
            ContentConfig.user_id == user.id,
            ContentConfig.config_key == config_key
        ).first()
        
        if config:
            config.config_value = config_value
        else:
            config = ContentConfig(
                id=str(uuid.uuid4()),
                user_id=user.id,
                config_key=config_key,
                config_value=config_value
            )
            db.add(config)
        
        db.commit()
        return {"message": "Config saved successfully", "config_key": config_key}
    else:
        # 批量保存配置
        config_data = {k: v for k, v in request.items() 
                      if k not in ["config_key", "config_value"]}
        
        saved_keys = []
        for key, value in config_data.items():
            config = db.query(ContentConfig).filter(
                ContentConfig.user_id == user.id,
                ContentConfig.config_key == key
            ).first()
            
            if config:
                config.config_value = value
            else:
                config = ContentConfig(
                    id=str(uuid.uuid4()),
                    user_id=user.id,
                    config_key=key,
                    config_value=value
                )
                db.add(config)
            
            saved_keys.append(key)
        
        db.commit()
        return {"message": "Config saved successfully", "saved_keys": saved_keys}
```

---

## 8. dependencies.py - 共享依赖

**文件**: `backend/dependencies.py`
**负责人**: 共同
**说明**: 存放共享的依赖函数和工具

```python
from datetime import datetime, timedelta
from typing import Optional
import uuid
from uuid import UUID
import hashlib
import jwt
import os
import httpx
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from fastapi import HTTPException, Header
from sqlalchemy.orm import Session

from database import get_db
from models import User

# ============== 配置 ==============

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "mediaflow-secret-key-change-in-production")
ALGORITHM = "HS256"

# SMTP 配置
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")

# ============== 工具函数 ==============

def hash_password(password: str) -> str:
    """哈希密码"""
    return hashlib.sha256(password.encode()).hexdigest()


def create_token(user_id: UUID) -> str:
    """创建 JWT Token"""
    payload = {"sub": str(user_id), "exp": datetime.utcnow() + timedelta(days=30)}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def generate_verification_code() -> str:
    """生成 6 位验证码"""
    import random
    return ''.join([str(random.randint(0, 9)) for _ in range(6)])


async def send_verification_email(email: str, code: str, purpose: str) -> bool:
    """发送验证码邮件
    
    Args:
        email: 收件人邮箱
        code: 验证码
        purpose: 用途（register/reset_password）
        
    Returns:
        发送成功返回 True，失败返回 False
    """
    subject = "【媒力 MediaFlow】验证码"
    purpose_text = "注册" if purpose == "register" else "重置密码"
    
    body = f"""您的验证码是：{code}

5 分钟内有效，请勿泄露给他人。

如非本人操作，请忽略此邮件。"""
    
    msg = MIMEMultipart()
    msg['From'] = SMTP_USER
    msg['To'] = email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain', 'utf-8'))
    
    max_retries = 3
    retry_delay = 2  # 秒
    
    for attempt in range(1, max_retries + 1):
        try:
            server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, [email], msg.as_string())
            server.quit()
            return True
            
        except Exception as e:
            if attempt < max_retries:
                import time
                time.sleep(retry_delay)
            else:
                print(f"Email send failed: {e}")
                return False
    
    return False


def get_current_user(
    authorization: Optional[str] = Header(None, alias="Authorization"),
    db: Session = Depends(get_db)
) -> User:
    """从 JWT Token 获取当前用户
    
    Args:
        authorization: Authorization header (Bearer token)
        db: 数据库会话
        
    Returns:
        当前用户对象
        
    Raises:
        401: 未认证或 Token 无效
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    token = authorization.replace("Bearer ", "")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    except Exception as e:
        print(f"Auth error: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")


async def extract_config_with_ai(message: str) -> dict:
    """使用 Kimi AI 提取配置
    
    Args:
        message: 用户消息
        
    Returns:
        提取的配置字典
    """
    kimi_api_key = os.getenv("KIMI_API_KEY")
    
    if not kimi_api_key:
        # 回退到基于规则的提取
        return extract_config_from_message(message)
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                "https://api.moonshot.cn/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {kimi_api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "moonshot-v1-8k",
                    "messages": [
                        {
                            "role": "system",
                            "content": """你是一个配置提取助手。从用户消息中提取小红书账号配置，返回 JSON 格式：
{
  "domain": "hiphop|food|emotion|beauty|travel",
  "content_style": "温暖治愈 | 犀利吐槽 | 专业干货 | 轻松搞笑",
  "publish_frequency": "daily|weekly|every_other_day",
  "publish_time": ["18:00", "20:00"],
  "image_source": "web|ai|mixed",
  "tags": ["标签 1", "标签 2"]
}
只返回 JSON，不要其他内容。"""
                        },
                        {"role": "user", "content": message}
                    ]
                }
            )
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            import json
            return json.loads(content)
    except Exception as e:
        print(f"Kimi AI error: {e}")
        return extract_config_from_message(message)


def extract_config_from_message(message: str) -> dict:
    """基于规则提取配置（回退方案）
    
    Args:
        message: 用户消息
        
    Returns:
        提取的配置字典
    """
    message_lower = message.lower()
    extracted = {}
    
    # 内容领域
    if any(kw in message_lower for kw in ["嘻哈", "说唱", "hip hop", "rap"]):
        extracted["domain"] = "hiphop"
    elif any(kw in message_lower for kw in ["美食", "探店", "餐厅", "小吃"]):
        extracted["domain"] = "food"
    elif any(kw in message_lower for kw in ["情感", "投稿", "恋爱", "心情"]):
        extracted["domain"] = "emotion"
    elif any(kw in message_lower for kw in ["美妆", "化妆", "护肤"]):
        extracted["domain"] = "beauty"
    elif any(kw in message_lower for kw in ["旅游", "旅行", "攻略"]):
        extracted["domain"] = "travel"
    
    # 内容风格
    if any(kw in message_lower for kw in ["温暖", "治愈", "温情"]):
        extracted["content_style"] = "温暖治愈"
    elif any(kw in message_lower for kw in ["犀利", "吐槽", "毒舌"]):
        extracted["content_style"] = "犀利吐槽"
    elif any(kw in message_lower for kw in ["专业", "干货", "教程"]):
        extracted["content_style"] = "专业干货"
    elif any(kw in message_lower for kw in ["轻松", "搞笑", "幽默"]):
        extracted["content_style"] = "轻松搞笑"
    
    # 发布频率
    if any(kw in message_lower for kw in ["每天", "天天", "日更"]):
        extracted["publish_frequency"] = "daily"
    elif any(kw in message_lower for kw in ["每周", "周更"]):
        extracted["publish_frequency"] = "weekly"
    elif any(kw in message_lower for kw in ["隔天", "每两天"]):
        extracted["publish_frequency"] = "every_other_day"
    
    # 发布时间
    if "早" in message_lower or "早上" in message_lower:
        extracted["publish_time"] = ["09:00", "10:00"]
    elif "晚" in message_lower or "晚上" in message_lower:
        extracted["publish_time"] = ["18:00", "20:00"]
    elif "中午" in message_lower or "午间" in message_lower:
        extracted["publish_time"] = ["12:00", "13:00"]
    
    # 图片来源
    if "网络" in message_lower or "抓取" in message_lower:
        extracted["image_source"] = "web"
    elif "ai" in message_lower or "生成" in message_lower:
        extracted["image_source"] = "ai"
    elif "混合" in message_lower:
        extracted["image_source"] = "mixed"
    
    # 标签
    tags = []
    if "热门" in message_lower or "热点" in message_lower:
        tags.append("热门")
    if "新歌" in message_lower or "新品" in message_lower:
        tags.append("新歌发布")
    if "明星" in message_lower or "艺人" in message_lower:
        tags.append("明星")
    if tags:
        extracted["tags"] = tags
    
    return extracted


def get_ai_response(user_input: str, extracted_config: dict) -> str:
    """生成 AI 响应
    
    Args:
        user_input: 用户输入
        extracted_config: 提取的配置
        
    Returns:
        AI 响应消息
    """
    input_lower = user_input.lower()
    
    if any(kw in input_lower for kw in ["嘻哈", "说唱", "hip hop"]):
        return "好的老板！嘻哈资讯很棒🎵 请问您想覆盖哪些内容？比如新歌发布、艺人动态、还是比赛资讯？我可以帮您从热门账号抓取内容，每天定时发布！"
    
    if any(kw in input_lower for kw in ["美食", "探店"]):
        return "美食探店是个好选择！🍜 您想做哪个城市的美食内容？我可以帮您整理本地热门餐厅、特色小吃，配上诱人的图片，保证吸引眼球！"
    
    if any(kw in input_lower for kw in ["情感", "投稿"]):
        return "情感类内容很受欢迎！💕 您想做什么风格？温暖治愈型还是犀利吐槽型？我会帮您筛选优质投稿，保持稳定更新！"
    
    if any(kw in input_lower for kw in ["时间", "发布", "几点"]):
        return "好的老板！发布时间很重要📅 我建议每天 18:00-20:00 发布，这个时段用户活跃度最高。您觉得怎么样？确认后我就开始自动运营了！"
    
    if any(kw in input_lower for kw in ["图片", "图"]):
        return "关于图片，我有几个选项：1️⃣ 从网络抓取相关图片 2️⃣ AI 生成配图 3️⃣ 混合模式（抓取+生成）您更喜欢哪种？"
    
    if extracted_config:
        config_parts = []
        if extracted_config.get("domain"):
            config_parts.append(f"内容领域：{extracted_config['domain']}")
        if extracted_config.get("content_style"):
            config_parts.append(f"风格：{extracted_config['content_style']}")
        if extracted_config.get("publish_frequency"):
            config_parts.append(f"频率：{extracted_config['publish_frequency']}")
        
        if config_parts:
            return f"明白了老板！✅ 我已经记下了您的偏好：{', '.join(config_parts)}。接下来我会先试发 3 篇内容给您预览，满意的话就正式开始自动运营。您还有什么特别要求吗？"
    
    return "明白了老板！✅ 我已经记下了您的偏好。接下来我会先试发 3 篇内容给您预览，满意的话就正式开始自动运营。您还有什么？"
```

---

## 9. routers/__init__.py - 统一注册

**文件**: `backend/routers/__init__.py`
**负责人**: 共同
**说明**: 统一注册所有 Router 模块

```python
from .auth import router as auth_router
from .users import router as users_router
from .lobsters import router as lobsters_router
from .chat import router as chat_router
from .contents import router as contents_router
from .publish import router as publish_router
from .config import router as config_router

# 导出所有 routers
__all__ = [
    "auth_router",
    "users_router",
    "lobsters_router",
    "chat_router",
    "contents_router",
    "publish_router",
    "config_router"
]
```

---

## 10. 重构后的 main.py

**文件**: `backend/main.py`
**说明**: 重构后的精简主入口文件

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import init_db

# 导入所有 routers
from routers import (
    auth_router,
    users_router,
    lobsters_router,
    chat_router,
    contents_router,
    publish_router,
    config_router
)

# 导入支付路由（已存在）
from payment import router as payment_router

app = FastAPI(title="MediaFlow API", version="1.0.0")

# ============== CORS 中间件 ==============

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============== 注册路由 ==============

# 核心模块
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(lobsters_router)
app.include_router(chat_router)
app.include_router(contents_router)
app.include_router(publish_router)
app.include_router(config_router)

# 支付模块
app.include_router(payment_router)

# ============== 启动事件 ==============

@app.on_event("startup")
def startup():
    """应用启动时初始化数据库"""
    init_db()


# ============== 健康检查 ==============

@app.get("/health")
def health():
    """健康检查端点"""
    return {"status": "ok", "version": "1.0.0"}


# ============== 主入口 ==============

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

---

## 📝 使用说明

### 步骤 1: 创建目录结构

```bash
cd backend
mkdir -p routers
touch routers/__init__.py
touch dependencies.py
```

### 步骤 2: 复制模板文件

1. 复制上述每个模块的代码到对应文件
2. 修改 `main.py`，使用重构后的版本
3. 复制 `dependencies.py` 的内容

### 步骤 3: 更新 main.py

用重构后的 `main.py` 替换原来的 `main.py`

### 步骤 4: 测试

```bash
cd backend
python -m uvicorn main:app --reload
```

访问 http://localhost:8000/docs 查看 API 文档

---

**文档结束**

**最后更新**: 2026-03-19
