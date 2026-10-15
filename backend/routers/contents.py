from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime
import uuid
import os
import shutil
import threading

from database import get_db
from models import User, Content, ContentStatus, XiaohongshuAccount
from dependencies import get_current_user, get_ai_service
from services.ai_service import AIService
from pydantic import BaseModel

router = APIRouter(prefix="/api/contents", tags=["contents"])


class ContentCreateRequest(BaseModel):
    title: str
    content: str
    tags: List[str] = []
    images: List[str] = []
    image_prompts: List[str] = []


def _get_owned_content(content_id: str, user: User, db: Session):
    """查找属于当前用户的内容（直接归属 user_id，或通过所属小红书账号归属）。"""
    content = db.query(Content).filter(Content.id == content_id).first()
    if not content:
        return None
    # 归属 1：直接挂在用户名下
    if content.user_id and content.user_id == user.id:
        return content
    # 归属 2：通过小红书账号
    if content.account_id:
        acc = db.query(XiaohongshuAccount).filter(
            XiaohongshuAccount.id == content.account_id,
            XiaohongshuAccount.user_id == user.id
        ).first()
        if acc:
            return content
    return None


@router.get("/{id}")
def get_content(
    id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    content = _get_owned_content(id, user, db)
    if not content:
        raise HTTPException(status_code=404, detail="内容不存在")
    return {
        "id": content.id,
        "title": content.title,
        "content": content.content,
        "tags": content.tags,
        "images": content.images,
        "image_prompts": content.image_prompts or [],
        "status": content.status.value,
        # 前端据此在重新进入页面时恢复"生成中"状态
        "image_status": content.image_status or "none",
        "quality_score": content.quality_score,
        "needs_review": bool(content.needs_review),
    }


@router.put("/{id}")
def update_content(
    id: str,
    request: ContentCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    content = _get_owned_content(id, user, db)
    if not content:
        raise HTTPException(status_code=404, detail="草稿不存在")

    content.title = request.title  # type: ignore
    content.content = request.content  # type: ignore
    content.tags = request.tags  # type: ignore
    content.images = request.images  # type: ignore
    if request.image_prompts:
        content.image_prompts = request.image_prompts  # type: ignore
    content.updated_at = datetime.utcnow()  # type: ignore

    db.commit()
    db.refresh(content)

    return {
        "id": content.id,
        "status": content.status.value
    }


@router.delete("/{id}")
def delete_content(
    id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    content = _get_owned_content(id, user, db)
    if not content:
        raise HTTPException(status_code=404, detail="草稿不存在")

    db.delete(content)
    db.commit()

    return {"success": True}


@router.post("")
def create_content(
    request: ContentCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Create new content draft（不挂具体账号的独立草稿，直接归属当前用户）
    content = Content(
        id=str(uuid.uuid4()),
        user_id=user.id,
        title=request.title,
        content=request.content,
        tags=request.tags,
        images=request.images,
        image_prompts=request.image_prompts,
        status=ContentStatus.draft,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    
    db.add(content)
    db.commit()
    db.refresh(content)
    
    return {
        "id": content.id,
        "status": content.status.value
    }


@router.get("")
def get_contents(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # 收集该用户所有内容归属（直接归属 + 通过小红书账号归属）
    account_ids = [
        a.id for a in db.query(XiaohongshuAccount.id).filter(
            XiaohongshuAccount.user_id == user.id
        ).all()
    ]

    from sqlalchemy import or_
    conditions = [Content.user_id == user.id]
    if account_ids:
        conditions.append(Content.account_id.in_(account_ids))

    contents = (
        db.query(Content)
        .filter(or_(*conditions))
        .order_by(Content.created_at.desc())
        .limit(50)
        .all()
    )
    return {"contents": [{
        "id": str(c.id),
        "title": c.title,
        "content": c.content,
        "images": c.images,
        "tags": c.tags,
        "status": c.status.value,
        "account_id": c.account_id,
        "published_at": c.published_at.isoformat() if c.published_at else None,  # type: ignore
        "created_at": c.created_at.isoformat()
    } for c in contents]}


def _recompute_image_status(c: Content) -> str:
    """按已产出的真实图片数决定配图状态。"""
    imgs = list(c.images or [])
    total = len(c.image_prompts or []) or len(imgs)
    real = len([u for u in imgs if u and "/uploads/" in u])
    if not total:
        return "none"
    if real >= total:
        return "done"
    return "partial" if real else "failed"


@router.post("/generate-image")
async def generate_single_image(
    request: dict,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    ai_service: AIService = Depends(get_ai_service)
):
    """根据单条图片提示词生成一张图片，返回本地 URL。

    同时把结果写回草稿并维护 image_status——否则这条路径对全局进度条
    完全不可见（用户点单张重新生成，顶部什么都不显示），
    而且重新生成的图在用户手动保存前是不落库的。
    """
    prompt_cn = request.get("prompt", "").strip()
    content_style = request.get("content_style", "")
    image_style = request.get("image_style", "")
    topic_title = request.get("topic_title", "")
    content_id = (request.get("content_id") or "").strip()
    index = request.get("index")

    if not prompt_cn:
        raise HTTPException(status_code=400, detail="prompt 不能为空")

    # 要写库就必须先验归属
    target = _get_owned_content(content_id, user, db) if content_id else None
    if content_id and not target:
        raise HTTPException(status_code=404, detail="内容不存在或无权限")

    if target is not None:
        target.image_status = "pending"
        db.commit()

    from services.image_service import ImageService
    img_svc = ImageService()
    if not img_svc.available:
        raise HTTPException(status_code=503, detail="图片生成服务未配置（OPENAI_API_KEY）")

    # build_image_prompt 和 generate 都是同步阻塞的网络调用（各自可能耗时几十秒）。
    # 直接在 async def 里调用会卡死整个事件循环——不只是这个请求慢，
    # 而是全站所有接口都不响应，前端表现为处处转圈。丢到线程池执行。
    import anyio

    def _work() -> tuple[str, str]:
        en = ai_service.build_image_prompt(
            chinese_description=prompt_cn,
            topic_title=topic_title,
            content_style=content_style,
            image_style=image_style,
        )
        return en, img_svc.generate(en)

    en_prompt, url = "", None
    try:
        en_prompt, url = await anyio.to_thread.run_sync(_work)

        # 结果直接落库：此前依赖前端事后单独 PUT，用户不保存就丢了
        if url and target is not None:
            imgs = list(target.images or [])
            idx = index if isinstance(index, int) and index >= 0 else len(imgs)
            while len(imgs) <= idx:
                imgs.append("")
            imgs[idx] = url
            prompts = list(target.image_prompts or [])
            while len(prompts) <= idx:
                prompts.append("")
            prompts[idx] = en_prompt
            target.images = imgs
            target.image_prompts = prompts
            target.updated_at = datetime.utcnow()
    finally:
        # 必须用 finally：客户端断开时抛的是 CancelledError，
        # 它是 BaseException 的子类，except Exception 捕获不到，
        # 状态会永远卡在 pending，进度条上挂着一个永不消失的幽灵任务。
        if target is not None:
            try:
                target.image_status = _recompute_image_status(target)
                db.commit()
            except Exception:
                db.rollback()

    if not url:
        raise HTTPException(status_code=500, detail="图片生成失败，请重试")

    return {"url": url, "prompt_used": en_prompt}


@router.post("/generate-all-images")
async def generate_all_images(
    request: dict,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    批量并行生成所有图片，通过 SSE 实时返回每张完成状态。
    支持多 API Key 轮询分配。
    """
    import asyncio
    import json as _json
    from fastapi.responses import StreamingResponse
    from concurrent.futures import ThreadPoolExecutor
    from services.image_service import ImageService

    prompts: list = request.get("prompts", [])
    content_id: str = request.get("content_id", "")

    # 只生成非空提示词，保留原索引以更新对应图片槽位
    valid = [(i, p) for i, p in enumerate(prompts) if p and str(p).strip()]
    if not valid:
        raise HTTPException(status_code=400, detail="没有有效的图片提示词")
    if not ImageService().available:
        raise HTTPException(status_code=503, detail="图片生成服务未配置（OPENAI_API_KEY）")

    import logging as _logging
    from database import SessionLocal
    _log = _logging.getLogger(__name__)

    loop = asyncio.get_running_loop()
    q: asyncio.Queue = asyncio.Queue()

    # 标记为生成中，让全局进度条能看到这个任务
    if content_id:
        c = db.query(Content).filter(Content.id == content_id).first()
        if c:
            c.image_status = "pending"
            db.commit()

    def _write_one(idx: int, url: str) -> None:
        """每张单独落库：整批做完才写的话，中途离开页面成果全丢，进度条也没有中间态。"""
        if not (content_id and url):
            return
        upd = SessionLocal()
        try:
            c = upd.query(Content).filter(Content.id == content_id).first()
            if c:
                imgs = list(c.images or [])
                while len(imgs) <= idx:
                    imgs.append("")
                imgs[idx] = url
                c.images = imgs
                c.updated_at = datetime.utcnow()
                upd.commit()
        except Exception as e:
            _log.warning(f"[BatchGen] 第{idx}张落库失败: {e}")
            upd.rollback()
        finally:
            upd.close()

    def _finalize() -> None:
        if not content_id:
            return
        upd = SessionLocal()
        try:
            c = upd.query(Content).filter(Content.id == content_id).first()
            if c:
                imgs = list(c.images or [])
                real = [u for u in imgs if u and "/uploads/" in u]
                c.image_status = ("done" if real and len(real) >= len(valid)
                                  else "partial" if real else "failed")
                c.updated_at = datetime.utcnow()
                upd.commit()
        except Exception as e:
            _log.warning(f"[BatchGen] 收尾失败: {e}")
            upd.rollback()
        finally:
            upd.close()

    def gen_one(idx: int, prompt: str):
        try:
            url = ImageService.for_index(idx).generate(prompt)
        except Exception as e:
            _log.warning(f"[BatchGen] 第{idx}张生成失败: {e}")
            url = None
        # 先落库再通知：即便 SSE 已断开，成果也已保存
        _write_one(idx, url or "")
        try:
            loop.call_soon_threadsafe(q.put_nowait, (idx, url))
        except RuntimeError:
            pass  # 事件循环已关闭（客户端早就走了），忽略即可

    def _run_all():
        """整批跑在后台线程里，不依赖 SSE 消费者存活。"""
        pool = ThreadPoolExecutor(max_workers=min(len(valid), 6))
        futures = [pool.submit(gen_one, i, p) for i, p in valid]
        for f in futures:
            try:
                f.result()
            except Exception:
                pass
        pool.shutdown(wait=False)
        _finalize()
        try:
            loop.call_soon_threadsafe(q.put_nowait, (None, None))
        except RuntimeError:
            pass

    # 关键：整个批次交给后台线程。用户中途切页面/关标签页，
    # 生成照常进行、照常落库，全局进度条也能继续显示。
    threading.Thread(target=_run_all, daemon=True, name=f"batchgen-{content_id[:8]}").start()

    async def event_stream():
        done = 0
        while done < len(valid):
            idx, url = await q.get()
            if idx is None:
                break
            done += 1
            ev = {"index": idx, "status": "done" if url else "error", "url": url or ""}
            yield f"data: {_json.dumps(ev)}\n\n"
        yield f"data: {_json.dumps({'type': 'complete'})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })


@router.post("/ai-modify")
async def ai_modify_content(
    request: dict,
    user: User = Depends(get_current_user),
    ai_service: AIService = Depends(get_ai_service)
):
    """AI 修改内容：接收全部字段（标题/正文/标签/图片提示词），返回修改后的版本。"""
    title         = request.get("title", "")
    content       = request.get("content", "")
    tags          = request.get("tags", [])
    image_prompts = request.get("image_prompts", [])
    requirement   = request.get("requirement", "")

    if not requirement:
        raise HTTPException(status_code=400, detail="请填写修改要求")

    tags_str = ", ".join(tags) if isinstance(tags, list) else tags
    prompts_str = "\n".join(
        f"  第{i+1}张：{p}" for i, p in enumerate(image_prompts)
    ) if image_prompts else "  （无配图说明）"

    prompt = f"""请对以下小红书图文内容按要求进行修改，返回修改后的完整内容。

【原始内容】
标题：{title}
正文：{content}
标签：{tags_str}
配图说明：
{prompts_str}

【修改要求】
{requirement}

【返回规则】
- 只返回 JSON，不要任何解释
- 没有要求修改的字段，原样返回
- image_prompts 数组长度可以根据需要调整
- JSON 格式：
{{
  "title": "修改后标题",
  "content": "修改后正文",
  "tags": ["标签1", "标签2"],
  "image_prompts": ["第1张说明", "第2张说明"]
}}"""

    import anyio
    import requests as _req, json as _json
    try:
        # 同步 HTTP 调用丢线程池，避免阻塞事件循环
        resp = await anyio.to_thread.run_sync(
            lambda: _req.post(
                f"{ai_service.endpoint}/chat/completions",
                headers={"Authorization": f"Bearer {ai_service.api_key}", "Content-Type": "application/json"},
                json={
                    "model": ai_service.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.7,
                    "response_format": {"type": "json_object"},
                },
                timeout=60,
            )
        )
        resp.raise_for_status()
        result = _json.loads(resp.json()["choices"][0]["message"]["content"])
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 修改失败：{str(e)}")


@router.post("/upload")
async def upload_image(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user)
):
    allowed_types = ["image/jpeg", "image/jpg", "image/png", "image/gif", "image/webp"]
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="只支持图片文件 (jpeg, jpg, png, gif, webp)")
    
    file_extension = file.filename.split(".")[-1] if (file.filename and "." in file.filename) else "jpg"
    unique_filename = f"{uuid.uuid4()}.{file_extension}"
    
    upload_dir = "backend/uploads"
    os.makedirs(upload_dir, exist_ok=True)
    
    file_path = os.path.join(upload_dir, unique_filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    return {"url": f"/uploads/{unique_filename}"}
