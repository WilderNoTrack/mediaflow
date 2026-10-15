from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import uuid
import anyio

from database import get_db
from models import User, PublishTask, PublishTaskStatus, XiaohongshuAccountBinding
from dependencies import get_current_user
from services.xiaohongshu_mcp import mcp_client
from services.multi_account_client import multi_account_client

router = APIRouter(prefix="/api/publish", tags=["publish"])


class PublishRequest(BaseModel):
    content_id: Optional[str] = None
    title: str
    content: str
    images: List[str] = []
    tags: List[str] = []
    scheduled_at: Optional[datetime] = None
    account_id: Optional[str] = None


class PublishResponse(BaseModel):
    success: bool
    task_id: str
    status: str
    message: str
    platform_url: Optional[str] = None


@router.post("/xiaohongshu", response_model=PublishResponse)
async def publish_to_xiaohongshu(
    req: PublishRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Create publish task first
    task = PublishTask(
        id=str(uuid.uuid4()),
        user_id=user.id,
        content_id=req.content_id,
        platform="xiaohongshu",
        status=PublishTaskStatus.pending,
        title=req.title,
        content=req.content,
        images=req.images,
        tags=req.tags,
        scheduled_at=req.scheduled_at
    )
    db.add(task)
    db.commit()
    
    try:
        task.status = PublishTaskStatus.publishing
        db.commit()
        
        # Handle multi-account vs single-account publishing
        if req.account_id:
            # Multi-account publishing: validate account ownership and use MultiAccountClient
            binding = db.query(XiaohongshuAccountBinding).filter(
                XiaohongshuAccountBinding.id == req.account_id,
                XiaohongshuAccountBinding.user_id == user.id
            ).first()
            
            if not binding:
                raise HTTPException(status_code=403, detail="账号不存在或不属于当前用户")
            
            # Check if multi-account manager is available
            if not await anyio.to_thread.run_sync(multi_account_client.health_check):
                raise HTTPException(status_code=503, detail="多账号管理器服务未启动")

            # Call MCP tool through MultiAccountClient
            # 发布走浏览器自动化，可能耗时几十秒。必须丢线程池，
            # 否则整个事件循环被占住，全站接口都不响应。
            result = await anyio.to_thread.run_sync(
                lambda: multi_account_client.call_mcp_tool(
                    binding.mcp_account_id,
                    "publish_note",
                    {
                        "title": req.title,
                        "content": req.content,
                        "images": req.images,
                        "tags": req.tags
                    }
                )
            )

        else:
            # Single-account publishing: use existing mcp_client (backward compatibility)
            if not await anyio.to_thread.run_sync(mcp_client.health_check):
                raise HTTPException(status_code=503, detail="MCP 服务未启动")

            result = await anyio.to_thread.run_sync(
                lambda: mcp_client.publish_note(
                    title=req.title,
                    content=req.content,
                    images=req.images,
                    tags=req.tags
                )
            )
        
        # Update task based on result
        if result.get("success"):
            task.status = PublishTaskStatus.published
            task.platform_note_id = result.get("note_id")
            task.platform_url = result.get("url")
            task.published_at = datetime.utcnow()
            db.commit()
            
            return PublishResponse(
                success=True,
                task_id=task.id,
                status="published",
                message="发布成功",
                platform_url=task.platform_url
            )
        else:
            task.status = PublishTaskStatus.failed
            task.error_message = result.get("error", "未知错误")
            db.commit()
            
            return PublishResponse(
                success=False,
                task_id=task.id,
                status="failed",
                message=f"发布失败：{task.error_message}"
            )
            
    except Exception as e:
        task.status = PublishTaskStatus.failed
        task.error_message = str(e)
        db.commit()
        
        return PublishResponse(
            success=False,
            task_id=task.id,
            status="failed",
            message=f"发布失败：{str(e)}"
        )


@router.get("/status/{task_id}")
async def get_publish_status(
    task_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    task = db.query(PublishTask).filter(
        PublishTask.id == task_id,
        PublishTask.user_id == user.id
    ).first()
    
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    return {
        "task_id": task.id,
        "platform": task.platform,
        "status": task.status.value,
        "title": task.title,
        "platform_url": task.platform_url,
        "error_message": task.error_message,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "published_at": task.published_at.isoformat() if task.published_at else None
    }


@router.get("/tasks")
async def list_publish_tasks(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    tasks = db.query(PublishTask).filter(
        PublishTask.user_id == user.id
    ).order_by(PublishTask.created_at.desc()).limit(20).all()
    
    return [{
        "task_id": task.id,
        "platform": task.platform,
        "status": task.status.value,
        "title": task.title,
        "platform_url": task.platform_url,
        "created_at": task.created_at.isoformat() if task.created_at else None
    } for task in tasks]
