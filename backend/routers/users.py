from collections import Counter
from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from database import get_db
from models import User, Subscription, XiaohongshuAccount, AccountStatus
from dependencies import get_current_user

router = APIRouter(prefix="/api/user", tags=["users"])


@router.get("/profile")
def get_profile(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    subscription = db.query(Subscription).filter(Subscription.user_id == user.id).first()
    xiaohongshu = db.query(XiaohongshuAccount).filter(
        XiaohongshuAccount.user_id == user.id,
        XiaohongshuAccount.status == AccountStatus.active
    ).first()
    
    return {
        "id": str(user.id),
        "phone": user.phone,
        "email": user.email,
        "nickname": user.nickname,
        "avatar_url": user.avatar_url,
        "created_at": user.created_at.isoformat(),
        "subscription": {
            "plan": subscription.plan.value if subscription else "basic",
            "status": subscription.status.value if subscription else "trial",
            "trial_end": subscription.trial_end.isoformat() if subscription and subscription.trial_end else None,  # type: ignore
            "expires_at": subscription.expires_at.isoformat() if subscription and subscription.expires_at else None  # type: ignore
        } if subscription else None,
        "xiaohongshu_account": {
            "id": str(xiaohongshu.id),
            "username": xiaohongshu.username,
            "status": xiaohongshu.status.value
        } if xiaohongshu else None
    }


from pydantic import BaseModel

class UpdateProfileRequest(BaseModel):
    nickname: str | None = None
    phone: str | None = None
    email: str | None = None
    avatar_url: str | None = None


@router.put("/profile")
def update_profile(
    req: UpdateProfileRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    from datetime import datetime
    
    # 更新用户信息
    if req.nickname:
        user.nickname = req.nickname
    if req.phone:
        user.phone = req.phone
    if req.email:
        user.email = req.email
    if req.avatar_url:
        user.avatar_url = req.avatar_url
    
    user.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    
    # 返回更新后的用户信息
    return {
        "id": str(user.id),
        "phone": user.phone,
        "email": user.email,
        "nickname": user.nickname,
        "avatar_url": user.avatar_url,
        "created_at": user.created_at.isoformat(),
        "updated_at": user.updated_at.isoformat()
    }


@router.post("/avatar")
def upload_avatar(
    file: bytes = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    from datetime import datetime
    import base64
    
    try:
        # 简单的文件验证（检查是否是图片）
        # 实际应用中应该更严格的验证
        allowed_types = ["image/jpeg", "image/png", "image/gif"]
        
        # 保存到本地或云存储（这里演示保存到数据库或返回base64）
        # 实际项目中应该保存到文件系统或云存储服务
        avatar_base64 = base64.b64encode(file).decode("utf-8")
        avatar_url = f"data:image/jpeg;base64,{avatar_base64}"
        
        user.avatar_url = avatar_url
        user.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(user)
        
        return {
            "message": "Avatar uploaded successfully",
            "avatar_url": user.avatar_url
        }
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=f"Failed to upload avatar: {str(e)}")


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str
    confirm_password: str


@router.post("/change-password")
def change_password(
    req: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    from fastapi import HTTPException
    
    # 验证新密码和确认密码是否一致
    if req.new_password != req.confirm_password:
        raise HTTPException(status_code=400, detail="New password and confirmation do not match")
    
    # 验证密码长度
    if len(req.new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters")
    
    # 验证旧密码是否正确
    from dependencies import hash_password
    if user.password_hash != hash_password(req.old_password):
        raise HTTPException(status_code=400, detail="Incorrect old password")
    
    # 更新密码
    from datetime import datetime
    user.password_hash = hash_password(req.new_password)
    user.updated_at = datetime.utcnow()
    db.commit()
    
    return {
        "message": "Password changed successfully"
    }


class NotificationSettingsRequest(BaseModel):
    publishSuccess: bool
    dataReport: bool
    systemUpdate: bool


@router.put("/notifications")
def update_notifications(
    req: NotificationSettingsRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    from datetime import datetime
    
    # 更新通知设置
    user.notification_settings = {
        "publishSuccess": req.publishSuccess,
        "dataReport": req.dataReport,
        "systemUpdate": req.systemUpdate,
    }
    user.updated_at = datetime.utcnow()
    db.commit()
    
    return {
        "message": "Notification settings updated successfully",
        "settings": user.notification_settings
    }


class DeleteAccountRequest(BaseModel):
    password: str


@router.delete("/account")
def delete_account(
    req: DeleteAccountRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    from fastapi import HTTPException
    
    # 验证密码是否正确
    from dependencies import hash_password
    if user.password_hash != hash_password(req.password):
        raise HTTPException(status_code=400, detail="Incorrect password")
    
    # 软删除或硬删除（这里演示硬删除，实际项目中推荐软删除）
    from models import (
        Subscription, XiaohongshuAccount, XiaohongshuAccountBinding,
        AccountConversation, Topic, Content, PublishLog,
    )

    account_ids = db.query(XiaohongshuAccount.id).filter(
        XiaohongshuAccount.user_id == user.id
    )
    content_ids = db.query(Content.id).filter(Content.account_id.in_(account_ids))

    # 删除相关数据（按外键依赖顺序：日志 → 内容 → 选题/对话 → 账号 → 订阅）
    db.query(PublishLog).filter(
        PublishLog.content_id.in_(content_ids)
    ).delete(synchronize_session=False)

    db.query(Content).filter(
        Content.account_id.in_(account_ids)
    ).delete(synchronize_session=False)

    db.query(Topic).filter(
        Topic.account_id.in_(account_ids)
    ).delete(synchronize_session=False)

    db.query(AccountConversation).filter(
        AccountConversation.account_id.in_(account_ids)
    ).delete(synchronize_session=False)

    db.query(XiaohongshuAccountBinding).filter(
        XiaohongshuAccountBinding.user_id == user.id
    ).delete(synchronize_session=False)
    db.query(XiaohongshuAccount).filter(XiaohongshuAccount.user_id == user.id).delete(synchronize_session=False)
    db.query(Subscription).filter(Subscription.user_id == user.id).delete(synchronize_session=False)

    # 删除用户
    db.delete(user)
    db.commit()
    
    return {
        "message": "Account deleted successfully"
    }


@router.get("/export-data")
def export_data(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    from fastapi import HTTPException
    from io import BytesIO
    from zipfile import ZipFile
    import json
    from datetime import datetime
    
    try:
        # 收集用户数据
        data = {
            "user": {
                "id": str(user.id),
                "email": user.email,
                "nickname": user.nickname,
                "phone": user.phone,
                "avatar_url": user.avatar_url,
                "bio": user.bio,
                "created_at": user.created_at.isoformat(),
                "updated_at": user.updated_at.isoformat(),
            },
            "subscription": None,
            "xiaohongshu_accounts": [],
            "topics": [],
            "conversations": [],
            "contents": [],
            "publish_logs": []
        }
        
        # 获取订阅信息
        from models import Subscription
        subscription = db.query(Subscription).filter(Subscription.user_id == user.id).first()
        if subscription:
            data["subscription"] = {
                "id": str(subscription.id),
                "plan": subscription.plan.value,
                "status": subscription.status.value,
                "trial_start": subscription.trial_start.isoformat() if subscription.trial_start else None,
                "trial_end": subscription.trial_end.isoformat() if subscription.trial_end else None,
                "expires_at": subscription.expires_at.isoformat() if subscription.expires_at else None,
                "created_at": subscription.created_at.isoformat(),
                "updated_at": subscription.updated_at.isoformat(),
            }
        
        # 获取小红书账号信息（含账号定位配置）
        from models import XiaohongshuAccount
        xiaohongshu_accounts = db.query(XiaohongshuAccount).filter(XiaohongshuAccount.user_id == user.id).all()
        data["xiaohongshu_accounts"] = [
            {
                "id": str(account.id),
                "username": account.username,
                "status": account.status.value,
                "theme": account.theme,
                "target_audience": account.target_audience,
                "content_style": account.content_style,
                "image_style": account.image_style,
                "topic_type": account.topic_type,
                "keywords": account.keywords,
                "requirements": account.requirements,
                "auto_enabled": bool(account.auto_enabled),
                "auto_frequency": account.auto_frequency,
                "created_at": account.created_at.isoformat(),
                "updated_at": account.updated_at.isoformat(),
            } for account in xiaohongshu_accounts
        ]

        account_ids = db.query(XiaohongshuAccount.id).filter(
            XiaohongshuAccount.user_id == user.id
        )

        # 获取选题库
        from models import Topic
        topics = db.query(Topic).filter(Topic.account_id.in_(account_ids)).all()
        data["topics"] = [
            {
                "id": str(t.id),
                "title": t.title,
                "angle": t.angle,
                "source": t.source,
                "hot_score": t.hot_score,
                "status": t.status.value if t.status else None,
                "created_at": t.created_at.isoformat(),
            } for t in topics
        ]

        # 获取账号对话历史
        from models import AccountConversation
        conversations = db.query(AccountConversation).filter(
            AccountConversation.account_id.in_(account_ids)
        ).all()
        data["conversations"] = [
            {
                "id": str(conv.id),
                "account_id": str(conv.account_id),
                "role": conv.role.value,
                "message": conv.message,
                "created_at": conv.created_at.isoformat(),
            } for conv in conversations
        ]

        # 获取内容信息
        from models import Content
        contents = db.query(Content).filter(Content.account_id.in_(account_ids)).all()
        data["contents"] = [
            {
                "id": str(content.id),
                "title": content.title,
                "content": content.content,
                "images": content.images,
                "tags": content.tags,
                "status": content.status.value,
                "scheduled_at": content.scheduled_at.isoformat() if content.scheduled_at else None,
                "published_at": content.published_at.isoformat() if content.published_at else None,
                "created_at": content.created_at.isoformat(),
                "updated_at": content.updated_at.isoformat(),
            } for content in contents
        ]
        
        # 获取发布日志
        from models import PublishLog
        publish_logs = db.query(PublishLog).filter(PublishLog.content_id.in_(
            db.query(Content.id).filter(Content.account_id.in_(account_ids))
        )).all()
        data["publish_logs"] = [
            {
                "id": str(log.id),
                "status": log.status.value,
                "error_message": log.error_message,
                "xiaohongshu_note_id": log.xiaohongshu_note_id,
                "created_at": log.created_at.isoformat(),
            } for log in publish_logs
        ]
        
        # 创建ZIP文件
        buffer = BytesIO()
        with ZipFile(buffer, "w") as zip_file:
            # 添加数据文件
            zip_file.writestr("data.json", json.dumps(data, ensure_ascii=False, indent=2))
            
            # 添加导出信息
            zip_file.writestr("README.txt", f"""
MediaFlow 数据导出
==================
导出时间: {datetime.utcnow().isoformat()}
用户ID: {user.id}

文件说明:
data.json - 包含所有用户数据的JSON文件
README.txt - 导出说明
            """)
        
        buffer.seek(0)
        
        from fastapi.responses import StreamingResponse
        return StreamingResponse(
            buffer,
            media_type="application/zip",
            headers={
                "Content-Disposition": f"attachment; filename=mediaflow-export-{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.zip"
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to export data: {str(e)}")
