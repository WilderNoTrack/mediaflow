"""
账号孵化工作台路由

每个小红书账号独立的工作空间：
- 账号配置（主题/受众/风格/要求）
- 与小媒对话配置账号
- 选题搜索与管理
- 内容生成（基于选题 + 账号配置）
- 内容列表
"""

import json as _json
import asyncio
import logging
import threading
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import uuid
import urllib.parse

from database import get_db
from models import (
    User, XiaohongshuAccount, Topic, TopicStatus, AccountStatus,
    Content, ContentStatus, AccountConversation, MessageRole
)
from dependencies import get_current_user, get_ai_service
from services.ai_service import AIService
from services.image_service import ImageService
from services.topic_search import search_topics

router = APIRouter(prefix="/api/workspace", tags=["workspace"])

PLACEHOLDER_COLORS = ["667eea", "d946ef", "f97316"]


def _check_account_owner(account_id: str, user: User, db: Session) -> XiaohongshuAccount:
    account = db.query(XiaohongshuAccount).filter(
        XiaohongshuAccount.id == account_id,
        XiaohongshuAccount.user_id == user.id
    ).first()
    if not account:
        raise HTTPException(status_code=404, detail="账号不存在或无权限")
    return account


def _make_placeholder(prompt: str, index: int) -> str:
    color = PLACEHOLDER_COLORS[index % len(PLACEHOLDER_COLORS)]
    text = urllib.parse.quote(prompt[:15] or "图片")
    return f"https://placehold.co/600x800/{color}/ffffff?text={text}"


# ─── 账号配置 ─────────────────────────────────────────────────────────────

class AccountProfileUpdate(BaseModel):
    theme: Optional[str] = None
    target_audience: Optional[str] = None
    content_style: Optional[str] = None
    image_style: Optional[str] = None
    topic_type: Optional[str] = None
    keywords: Optional[List[str]] = None
    requirements: Optional[List[str]] = None


class AccountCreateRequest(BaseModel):
    name: str


@router.post("/accounts")
def create_workspace_account(
    req: AccountCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    创建一个孵化账号（MediaFlow 内部账号单元）。
    不依赖外部多账号管理器，直接在数据库建记录。
    """
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="账号名称不能为空")

    account = XiaohongshuAccount(
        id=str(uuid.uuid4()),
        user_id=user.id,
        username=name,
        nickname=name,
        status=AccountStatus.active,
    )
    db.add(account)
    db.commit()
    db.refresh(account)

    return {
        "id": account.id,
        "username": account.username,
        "nickname": account.nickname,
        "theme": account.theme,
        "status": account.status.value,
        "draft_count": 0,
        "published_count": 0,
        "created_at": account.created_at.isoformat(),
    }


@router.get("/accounts")
def list_user_accounts(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """列出当前用户的所有小红书账号（含孵化配置摘要）。"""
    accounts = db.query(XiaohongshuAccount).filter(
        XiaohongshuAccount.user_id == user.id
    ).order_by(XiaohongshuAccount.created_at.desc()).all()

    result = []
    for acc in accounts:
        draft_count = db.query(Content).filter(
            Content.account_id == acc.id,
            Content.status == ContentStatus.draft
        ).count()
        published_count = db.query(Content).filter(
            Content.account_id == acc.id,
            Content.status == ContentStatus.published
        ).count()
        result.append({
            "id": acc.id,
            "username": acc.username,
            "nickname": acc.nickname,
            "avatar_url": acc.avatar_url,
            "theme": acc.theme,
            "target_audience": acc.target_audience,
            "status": acc.status.value,
            "draft_count": draft_count,
            "published_count": published_count,
            "created_at": acc.created_at.isoformat(),
        })
    return {"accounts": result}


@router.get("/accounts/{account_id}/profile")
def get_account_profile(
    account_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取账号完整配置。"""
    acc = _check_account_owner(account_id, user, db)
    return {
        "id": acc.id,
        "username": acc.username,
        "nickname": acc.nickname,
        "avatar_url": acc.avatar_url,
        "theme": acc.theme,
        "target_audience": acc.target_audience,
        "content_style": acc.content_style,
        "image_style": acc.image_style,
        "topic_type": acc.topic_type,
        "keywords": acc.keywords or [],
        "requirements": acc.requirements or [],
        "status": acc.status.value,
    }


@router.put("/accounts/{account_id}/profile")
def update_account_profile(
    account_id: str,
    req: AccountProfileUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """更新账号配置（主题/受众/风格/要求）。"""
    acc = _check_account_owner(account_id, user, db)
    if req.theme is not None:
        acc.theme = req.theme  # type: ignore
    if req.target_audience is not None:
        acc.target_audience = req.target_audience  # type: ignore
    if req.content_style is not None:
        acc.content_style = req.content_style  # type: ignore
    if req.image_style is not None:
        acc.image_style = req.image_style  # type: ignore
    if req.topic_type is not None:
        acc.topic_type = req.topic_type  # type: ignore
    if req.keywords is not None:
        acc.keywords = req.keywords  # type: ignore
    if req.requirements is not None:
        acc.requirements = req.requirements  # type: ignore
    acc.updated_at = datetime.utcnow()  # type: ignore
    db.commit()
    return {"message": "账号配置已更新"}


# ─── 账号对话配置（和小媒聊天设定主题） ──────────────────────────────────

@router.post("/accounts/{account_id}/chat")
async def account_chat(
    account_id: str,
    request: dict,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    ai_service: AIService = Depends(get_ai_service)
):
    """
    与小媒对话来设定/完善账号的运营定位。
    小媒会通过对话提取：主题、受众、内容风格、禁忌要求。
    """
    acc = _check_account_owner(account_id, user, db)
    message = request.get("message", "")
    if not message:
        raise HTTPException(status_code=400, detail="消息不能为空")

    system_prompt = f"""你是小媒，正在帮用户完成小红书账号（@{acc.username or acc.nickname or '新账号'}）的运营配置。

【你的工作分两步】

第一步：确定账号整体定位
- 账号发什么方向的内容（大主题）
- 目标受众是谁
- 内容风格和调性
- 配图结构（封面/步骤/成品等安排）
- 特别要求或禁忌

第二步：确定选题类型
- 问清楚"每篇帖子围绕什么类别来发"，一个短语即可
- 例：穿搭号→"通勤穿搭场景"、学习号→"考研知识点"、做饭号→"家常菜品"
- 只问清楚类别，不需要生成具体的词（那是选题页面的工作）

第三步：确定配图的视觉风格（这非常重要，不能跳过）
- 不是问"几张图"，而是问图片要呈现什么感觉
- 举几个例子帮用户想清楚：
  · "随手拍的生活感，就是普通手机拍的那种，有点粗糙也没关系"
  · "卡通插画风格，不要真实照片"
  · "专业摄影风格，精致好看的那种"
  · "纪录片感，记录过程的真实状态"
  · "小清新，背景干净，自然光"
- 用户说什么就记什么，原话保留，这会直接影响生成的图片风格

⚠️ 绝对不要写文案、示例帖子或正文内容。如果用户要你写，说：「文案生成在"选题"Tab，配置好后去那里。」

对话原则：
- 每次只问 1 个问题
- 回复简短不超过 100 字
- 语气轻松
- 提问末尾加选项：【OPTIONS】选项1||选项2||选项3||其他（自定义）
- 选项要具体，最后一个永远是"其他（自定义）"
- 全部收集完后给出总结：✅ 账号定位确认：[总结]，提示"保存配置"
- 总结后不再追加 OPTIONS"""

    # 加载历史对话
    history = db.query(AccountConversation).filter(
        AccountConversation.account_id == account_id
    ).order_by(AccountConversation.created_at.desc()).limit(10).all()

    conversation_history = [
        {"role": m.role.value, "content": m.message}
        for m in reversed(history)
    ]

    messages = (
        [{"role": "system", "content": system_prompt}]
        + conversation_history
        + [{"role": "user", "content": message}]
    )

    # 同步 HTTP 调用必须丢线程池：直接在 async def 里跑会卡死整个事件循环，
    # 表现为全站所有接口都不响应
    import anyio
    import requests as req_lib
    resp = await anyio.to_thread.run_sync(
        lambda: req_lib.post(
            f"{ai_service.endpoint}/chat/completions",
            headers={"Authorization": f"Bearer {ai_service.api_key}", "Content-Type": "application/json"},
            json={"model": ai_service.model, "messages": messages, "temperature": 1.0},
            timeout=30,
        )
    )
    if resp.status_code != 200:
        raise HTTPException(status_code=500, detail="AI 服务调用失败")

    response_text = resp.json()["choices"][0]["message"]["content"]

    # 解析 OPTIONS 标记
    options: list = []
    if "【OPTIONS】" in response_text:
        parts = response_text.split("【OPTIONS】", 1)
        message_text = parts[0].strip()
        options = [o.strip() for o in parts[1].split("||") if o.strip()]
    else:
        message_text = response_text

    # 保存对话记录（保存完整原始文本含OPTIONS标记）
    db.add(AccountConversation(
        id=str(uuid.uuid4()), account_id=account_id,
        role=MessageRole.user, message=message
    ))
    db.add(AccountConversation(
        id=str(uuid.uuid4()), account_id=account_id,
        role=MessageRole.assistant, message=response_text
    ))
    db.commit()

    return {"response": message_text, "options": options}


@router.get("/accounts/{account_id}/chat-history")
def get_account_chat_history(
    account_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    _check_account_owner(account_id, user, db)
    history = db.query(AccountConversation).filter(
        AccountConversation.account_id == account_id
    ).order_by(AccountConversation.created_at.asc()).limit(50).all()
    return {"history": [
        {"role": m.role.value, "message": m.message, "created_at": m.created_at.isoformat()}
        for m in history
    ]}


@router.post("/accounts/{account_id}/extract-config")
async def extract_config_from_chat(
    account_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    ai_service: AIService = Depends(get_ai_service)
):
    """
    分析账号对话历史，提取并自动保存账号定位配置。
    """
    acc = _check_account_owner(account_id, user, db)

    history = db.query(AccountConversation).filter(
        AccountConversation.account_id == account_id
    ).order_by(AccountConversation.created_at.asc()).limit(50).all()

    if not history:
        raise HTTPException(status_code=400, detail="请先和小媒对话配置账号定位")

    # 优先找最近一条包含「✅ 账号定位确认」的小媒消息，以它为准
    latest_confirm = None
    for m in reversed(history):
        if m.role == MessageRole.assistant and "账号定位确认" in m.message:
            latest_confirm = m.message
            break

    if latest_confirm:
        primary_source = f"""最终确认的账号定位（以此为准）：
{latest_confirm}"""
        extra_context = ""
    else:
        # 没有确认消息，用全部对话
        primary_source = "对话记录（尚未有最终确认，尽量提取）：\n" + "\n".join(
            f"{'用户' if m.role == MessageRole.user else '小媒'}: {m.message}"
            for m in history
        )
        extra_context = ""

    prompt = f"""从以下内容中提取账号配置信息，返回 JSON。

{primary_source}
{extra_context}

【提取规则】

1. theme：账号主题，一句话概括。

2. target_audience：目标受众，一句话。

3. content_style：文字内容的风格和调性，不要包含图片描述。

4. image_style：完整提取图片相关的所有信息，包括：
   - 图片结构顺序（如"封面效果图→过程图→细节图"）
   - 视觉风格细节（背景、光效、视角要求、质感描述等）
   - 特别注意：若有详细的风格说明（如背景、视角、整体要求），必须完整保留，不要缩减
   - 格式："[结构]；[视觉风格完整描述]"

5. topic_type：每篇帖子的选题类别（如"穿搭场景"/"菜品名"/"知识点"），没有则 null。

6. requirements：文案层面的禁忌/要求，图片相关的已在 image_style，这里只放文案要求。

7. keywords：对话中明确出现的具体选题词，原话记录，没有则 []。

返回纯 JSON：
{{
  "theme": "...",
  "target_audience": "...",
  "content_style": "...",
  "image_style": "...",
  "topic_type": "...",
  "requirements": [],
  "keywords": []
}}"""

    # 同步 HTTP 调用丢线程池，避免阻塞事件循环
    import anyio
    import requests as req_lib
    resp = await anyio.to_thread.run_sync(
        lambda: req_lib.post(
            f"{ai_service.endpoint}/chat/completions",
            headers={"Authorization": f"Bearer {ai_service.api_key}", "Content-Type": "application/json"},
            json={
                "model": ai_service.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "response_format": {"type": "json_object"}
            },
            timeout=30,
        )
    )
    if resp.status_code != 200:
        raise HTTPException(status_code=500, detail="AI 分析失败")

    extracted = ai_service._extract_json(resp.json()["choices"][0]["message"]["content"])

    if extracted.get("theme"):
        acc.theme = extracted["theme"]  # type: ignore
    if extracted.get("target_audience"):
        acc.target_audience = extracted["target_audience"]  # type: ignore
    if extracted.get("content_style"):
        acc.content_style = extracted["content_style"]  # type: ignore
    if extracted.get("image_style"):
        acc.image_style = extracted["image_style"]  # type: ignore
    if extracted.get("topic_type"):
        acc.topic_type = extracted["topic_type"]  # type: ignore
    if extracted.get("requirements"):
        acc.requirements = extracted["requirements"]  # type: ignore
    if extracted.get("keywords"):
        acc.keywords = extracted["keywords"]  # type: ignore
    acc.updated_at = datetime.utcnow()  # type: ignore
    db.commit()

    return {
        "message": "账号定位已保存",
        "config": extracted,
        "saved": {
            "theme": acc.theme,
            "target_audience": acc.target_audience,
            "content_style": acc.content_style,
            "image_style": acc.image_style,
            "keywords": acc.keywords or [],
            "requirements": acc.requirements or [],
        }
    }


# ─── 选题管理 ─────────────────────────────────────────────────────────────

@router.post("/accounts/{account_id}/suggest-keywords")
def suggest_keywords(
    account_id: str,
    request: dict = {},
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    ai_service: AIService = Depends(get_ai_service),
):
    """根据账号的选题类型，生成一批具体的选题词。"""
    acc = _check_account_owner(account_id, user, db)
    exclude: list = request.get("exclude", []) if request else []

    # 优先用 topic_type 来生成具体词
    if acc.topic_type:
        profile_desc = "\n".join(filter(None, [
            f"选题类型：{acc.topic_type}",
            f"账号主题：{acc.theme}" if acc.theme else None,
            f"已有选题词：{', '.join(acc.keywords or [])}" if acc.keywords else None,
            f"已推荐过（不要重复）：{', '.join(exclude)}" if exclude else None,
        ]))
    else:
        profile_desc = "\n".join(filter(None, [
            f"账号主题：{acc.theme}" if acc.theme else None,
            f"目标受众：{acc.target_audience}" if acc.target_audience else None,
            f"内容风格：{acc.content_style}" if acc.content_style else None,
            f"已有关键词：{', '.join(acc.keywords or [])}" if acc.keywords else None,
            f"已推荐过（不要重复）：{', '.join(exclude)}" if exclude else None,
        ])) or "未设定账号定位"

    try:
        keywords = ai_service.suggest_keywords(profile_desc)
        # 服务端也过滤掉已出现的
        exclude_set = set(exclude)
        keywords = [k for k in keywords if k not in exclude_set]
        return {"keywords": keywords}
    except Exception:
        return {"keywords": [k for k in (acc.keywords or []) if k not in set(exclude)]}


class TopicSearchRequest(BaseModel):
    keyword: str
    platforms: List[str] = ["xiaohongshu", "bilibili", "douyin", "weibo", "baidu", "weixin"]


@router.post("/accounts/{account_id}/search-topics-stream")
def search_topics_stream(
    account_id: str,
    req: TopicSearchRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """流式搜索选题：每个平台完成后立即返回进度，最后返回 AI 综合结果。"""
    from services.topic_search import (
        search_xiaohongshu, search_bilibili, search_weibo,
        search_baidu, search_weixin, _search_douyin_with_fallback,
        _simulate_platform_trends, _analyze_and_suggest_topics
    )
    acc = _check_account_owner(account_id, user, db)
    theme = acc.theme or req.keyword
    requirements = acc.requirements or []

    fetch_map = {
        "xiaohongshu": ("小红书",   lambda: search_xiaohongshu(req.keyword, limit=20)),
        "bilibili":    ("B站",      lambda: search_bilibili(req.keyword, limit=20)),
        "weibo":       ("微博",     lambda: search_weibo(req.keyword, limit=20)),
        "baidu":       ("百度",     lambda: search_baidu(req.keyword, limit=20)),
        "weixin":      ("微信文章", lambda: search_weixin(req.keyword, limit=20)),
        "douyin":      ("抖音",     lambda: _search_douyin_with_fallback(req.keyword, limit=20)),
    }

    def event_stream():
        platforms_data = {}
        for pid in req.platforms:
            if pid not in fetch_map:
                continue
            label, fetcher = fetch_map[pid]
            # 发送"开始搜索"
            yield f"data: {_json.dumps({'type':'platform_start','platform':pid,'label':label})}\n\n"
            try:
                data = fetcher() or []
                ai_generated = False
                if not data:
                    simulated = _simulate_platform_trends(req.keyword, pid, theme)
                    if simulated:
                        data = simulated
                        ai_generated = True
                platforms_data[pid] = data
                items_preview = [
                    {
                        "title": it.get("title",""),
                        "hot_value": it.get("hot_value",""),
                        "url": it.get("url",""),
                        "note_id": it.get("note_id",""),
                        "xsec_token": it.get("xsec_token",""),
                        "bvid": it.get("bvid",""),
                        "author": it.get("author",""),
                        "cover": it.get("cover",""),
                        "snippet": it.get("snippet",""),
                    }
                    for it in data
                    if it.get("title")
                ]
                yield f"data: {_json.dumps({'type':'platform_done','platform':pid,'label':label,'count':len(items_preview),'items':items_preview,'ai_generated':ai_generated})}\n\n"
            except Exception as e:
                yield f"data: {_json.dumps({'type':'platform_error','platform':pid,'label':label,'error':str(e)})}\n\n"

        # AI 综合分析
        yield f"data: {_json.dumps({'type':'analyzing'})}\n\n"
        try:
            suggestions = _analyze_and_suggest_topics(
                keyword=req.keyword, theme=theme,
                target_audience=acc.target_audience or "",
                requirements=requirements, platforms_data=platforms_data,
            )
            # 保存选题
            saved = []
            for item in suggestions:
                topic = Topic(
                    id=str(uuid.uuid4()), account_id=account_id,
                    title=item.get("title",""), angle=item.get("angle",""),
                    source=item.get("source","ai"), hot_score=str(item.get("hot_score",3)),
                    status=TopicStatus.suggested,
                )
                db.add(topic)
                saved.append({"id":topic.id,"title":topic.title,"angle":topic.angle,
                               "source":topic.source,"hot_score":topic.hot_score,"status":topic.status.value})
            db.commit()
            yield f"data: {_json.dumps({'type':'complete','topics':saved})}\n\n"
        except Exception as e:
            yield f"data: {_json.dumps({'type':'error','error':str(e)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})


@router.get("/bilibili-video-detail")
def bilibili_video_detail(
    bvid: str,
    user: User = Depends(get_current_user),
):
    """调 B站公开 API 获取视频详情 + 热门评论。"""
    import requests as _req
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.bilibili.com"}
    try:
        # 视频基本信息
        view = _req.get(
            "https://api.bilibili.com/x/web-interface/view",
            params={"bvid": bvid}, headers=headers, timeout=10,
        ).json().get("data", {})
        aid = view.get("aid", 0)
        owner = view.get("owner", {})
        stat = view.get("stat", {})

        # 热门评论（按热度排序）
        comments = []
        if aid:
            try:
                cr = _req.get(
                    "https://api.bilibili.com/x/v2/reply",
                    params={"type": 1, "oid": aid, "sort": 2, "ps": 15},
                    headers=headers, timeout=10,
                ).json()
                for c in (cr.get("data", {}).get("replies") or [])[:15]:
                    comments.append({
                        "author": c.get("member", {}).get("uname", ""),
                        "content": c.get("content", {}).get("message", ""),
                        "like": c.get("like", 0),
                    })
            except Exception:
                pass

        return {
            "title": view.get("title", ""),
            "desc": view.get("desc", ""),
            "author": owner.get("name", ""),
            "view": stat.get("view", 0),
            "reply": stat.get("reply", 0),
            "comments": comments,
            "url": f"https://www.bilibili.com/video/{bvid}",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class XhsNoteDetailRequest(BaseModel):
    note_id: str
    xsec_token: str = ""


@router.post("/xhs-note-detail")
def xhs_note_detail(
    req: XhsNoteDetailRequest,
    user: User = Depends(get_current_user),
):
    """通过 MCP 获取小红书笔记详情（正文、图片、评论）。"""
    import requests as _req
    XHS_MCP_URL = "http://localhost:18060"
    try:
        resp = _req.post(
            f"{XHS_MCP_URL}/api/v1/feeds/detail",
            json={"feed_id": req.note_id, "xsec_token": req.xsec_token, "load_all_comments": False},
            timeout=30,
            proxies={"http": None, "https": None},
        )
        if resp.status_code == 200:
            body = resp.json()
            # MCP 响应结构: body.data.data.note（有两层 data）
            outer = body.get("data", {})
            data = outer.get("data", outer)  # 兼容单层和双层
            note = data.get("note", {})
            comments = data.get("comments", {}).get("list", [])
            return {
                "title": note.get("title", ""),
                "desc": note.get("desc", ""),
                "author": note.get("user", {}).get("nickname", ""),
                "avatar": note.get("user", {}).get("avatar", ""),
                "ip_location": note.get("ipLocation", ""),
                "liked_count": note.get("interactInfo", {}).get("likedCount", ""),
                "comment_count": note.get("interactInfo", {}).get("commentCount", ""),
                "collected_count": note.get("interactInfo", {}).get("collectedCount", ""),
                "images": [img.get("urlDefault", "") for img in note.get("imageList", [])],
                "comments": [
                    {"author": c.get("userInfo", {}).get("nickname", ""), "content": c.get("content", "")}
                    for c in comments[:10]
                ],
                "url": f"https://www.xiaohongshu.com/explore/{req.note_id}",
            }
        import logging; logging.getLogger(__name__).warning(f"[XHS详情] MCP返回 {resp.status_code}: {resp.text[:300]}")
        return {"error": f"MCP 返回 {resp.status_code}: {resp.text[:200]}"}
    except Exception as e:
        import logging; logging.getLogger(__name__).error(f"[XHS详情] 异常: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/weixin-article-detail")
def weixin_article_detail(
    url: str,
    user: User = Depends(get_current_user),
):
    """获取微信公众号文章详情（仅支持直接 mp.weixin.qq.com 链接）。"""
    import requests as _req
    import html as _html

    # Sogou redirect links are blocked by antispider — can't fetch
    if "sogou.com" in url:
        return {"sogou_blocked": True, "url": url}

    try:
        resp = _req.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15",
                "Referer": "https://mp.weixin.qq.com/",
                "Accept-Language": "zh-CN,zh;q=0.9",
            },
            allow_redirects=True,
            timeout=15,
        )
        if resp.status_code != 200:
            return {"error": f"获取失败 ({resp.status_code})"}

        text = resp.text
        final_url = str(resp.url)

        # Author
        author = ""
        am = re.search(r'var nickname\s*=\s*"([^"]+)"', text)
        if not am:
            am = re.search(r'"nickname"\s*:\s*"([^"]+)"', text)
        if am:
            author = _html.unescape(am.group(1)).strip()

        # Publish time
        pub_time = ""
        pt = re.search(r'var ct\s*=\s*"(\d+)"', text)
        if pt:
            import datetime
            try:
                pub_time = datetime.datetime.fromtimestamp(int(pt.group(1))).strftime("%Y-%m-%d %H:%M")
            except Exception:
                pass

        # Content via BeautifulSoup
        content = ""
        try:
            from bs4 import BeautifulSoup as _BS4
            soup = _BS4(text, "html.parser")
            content_el = soup.find(id="js_content")
            if content_el:
                for noise in content_el(["script", "style", "img"]):
                    noise.decompose()
                # leaf paragraphs only (no nested p)
                paras = [
                    p.get_text(strip=True)
                    for p in content_el.find_all(["p", "section"])
                    if p.get_text(strip=True) and not p.find(["p", "section"])
                ]
                content = "\n\n".join(paras[:80])
        except Exception:
            pass

        return {
            "author": author,
            "pub_time": pub_time,
            "content": content[:3000],
            "url": final_url,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/weibo-detail")
def weibo_detail(
    url: str,
    user: User = Depends(get_current_user),
):
    """获取微博热搜话题相关帖子（需要 WEIBO_COOKIE）。"""
    import requests as _req
    import html as _html
    import os as _os
    WEIBO_COOKIE = _os.getenv("WEIBO_COOKIE", "")

    # Without cookie, Weibo always redirects to login — skip fetch entirely
    if not WEIBO_COOKIE:
        return {"needs_login": True, "url": url}

    try:
        resp = _req.get(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Referer": "https://weibo.com/",
            "Cookie": WEIBO_COOKIE,
            "Accept-Language": "zh-CN,zh;q=0.9",
        }, timeout=15, allow_redirects=True)

        if resp.status_code != 200 or "passport.weibo" in str(resp.url):
            return {"needs_login": True, "url": url}

        posts = []
        try:
            from bs4 import BeautifulSoup as _BS4
            soup = _BS4(resp.text, "html.parser")
            for card in soup.select("div.card-wrap[mid]")[:12]:
                txt_el = card.select_one("p.txt") or card.select_one(".txt")
                if not txt_el:
                    continue
                text = re.sub(r"\s*全文\s*$", "", txt_el.get_text(separator=" ", strip=True)).strip()
                if not text or len(text) < 5:
                    continue
                name_el = card.select_one(".name")
                like_el = card.select_one("[node-type='like_status'] em")
                posts.append({
                    "author": name_el.get_text(strip=True) if name_el else "",
                    "content": text,
                    "likes": like_el.get_text(strip=True) if like_el else "",
                })
        except ImportError:
            pass

        return {"posts": posts, "url": url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/baidu-link-detail")
def baidu_link_detail(
    url: str,
    user: User = Depends(get_current_user),
):
    """跟随百度跳转链接，抓取目标文章内容。"""
    import requests as _req
    import html as _html
    try:
        hdrs = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Accept": "text/html,*/*;q=0.8",
            "Referer": "https://www.baidu.com/",
        }
        resp = _req.get(url, headers=hdrs, allow_redirects=True, timeout=15)
        if resp.status_code != 200 or len(resp.text) < 3000:
            return {"fetch_failed": True, "url": url}

        final_url = str(resp.url)
        text = resp.text

        # Try BeautifulSoup for structured extraction
        title = ""
        content = ""
        try:
            from bs4 import BeautifulSoup as _BS4
            soup = _BS4(text, "html.parser")
            # Remove noise
            for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
                tag.decompose()
            # Title
            title_el = soup.select_one("h1, .article-title, .title, [class*='title']")
            if not title_el:
                title_el = soup.find("title")
            title = title_el.get_text(strip=True)[:200] if title_el else ""
            # Content: try common article containers
            article_el = soup.select_one(
                "article, .article, .article-content, .content, #content, "
                ".main-content, .post-content, .entry-content, #js_content"
            )
            if article_el:
                paras = [p.get_text(strip=True) for p in article_el.find_all(["p", "li"]) if p.get_text(strip=True)]
                content = "\n\n".join(paras[:40])
            else:
                paras = [p.get_text(strip=True) for p in soup.find_all("p") if len(p.get_text(strip=True)) > 30]
                content = "\n\n".join(paras[:30])
        except ImportError:
            tm = re.search(r'<title>(.*?)</title>', text, re.DOTALL)
            title = _html.unescape(re.sub(r"<[^>]+>", "", tm.group(1))).strip() if tm else ""
            paras = re.findall(r'<p[^>]*>(.{30,}?)</p>', text, re.DOTALL)
            content = "\n\n".join(
                _html.unescape(re.sub(r"<[^>]+>", "", p)).strip()
                for p in paras[:30]
            )

        if not content:
            return {"fetch_failed": True, "title": title, "url": final_url}

        return {
            "title": title,
            "content": content[:3000],
            "url": final_url,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/accounts/{account_id}/search-topics")
def search_account_topics(
    account_id: str,
    req: TopicSearchRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    多平台搜索选题热点 + AI 综合分析，返回 8-10 个选题建议并保存到数据库。
    """
    acc = _check_account_owner(account_id, user, db)

    theme = acc.theme or req.keyword
    target_audience = acc.target_audience or ""
    requirements = acc.requirements or []

    suggestions = search_topics(
        keyword=req.keyword,
        theme=theme,
        target_audience=target_audience,
        requirements=requirements,
        platforms=req.platforms,
    )

    # 保存到 Topic 表
    saved = []
    for item in suggestions:
        topic = Topic(
            id=str(uuid.uuid4()),
            account_id=account_id,
            title=item.get("title", ""),
            angle=item.get("angle", ""),
            source=item.get("source", "ai"),
            hot_score=str(item.get("hot_score", 3)),
            status=TopicStatus.suggested,
        )
        db.add(topic)
        saved.append({
            "id": topic.id,
            "title": topic.title,
            "angle": topic.angle,
            "source": topic.source,
            "hot_score": topic.hot_score,
            "status": topic.status.value,
        })
    db.commit()

    return {"topics": saved, "keyword": req.keyword}


@router.get("/accounts/{account_id}/topics")
def list_account_topics(
    account_id: str,
    status: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取账号的选题列表。"""
    _check_account_owner(account_id, user, db)
    q = db.query(Topic).filter(Topic.account_id == account_id)
    if status:
        try:
            q = q.filter(Topic.status == TopicStatus(status))
        except ValueError:
            pass
    topics = q.order_by(Topic.created_at.desc()).limit(50).all()
    return {"topics": [
        {
            "id": t.id,
            "title": t.title,
            "angle": t.angle,
            "source": t.source,
            "hot_score": t.hot_score,
            "status": t.status.value,
            "created_at": t.created_at.isoformat(),
        }
        for t in topics
    ]}


@router.put("/accounts/{account_id}/topics/{topic_id}/status")
def update_topic_status(
    account_id: str,
    topic_id: str,
    request: dict,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """更新选题状态（selected / skipped / suggested）。"""
    _check_account_owner(account_id, user, db)
    topic = db.query(Topic).filter(Topic.id == topic_id, Topic.account_id == account_id).first()
    if not topic:
        raise HTTPException(status_code=404, detail="选题不存在")
    status_val = request.get("status", "selected")
    try:
        topic.status = TopicStatus(status_val)  # type: ignore
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的状态值")
    db.commit()
    return {"message": "状态已更新"}


# ─── 内容生成（基于选题 + 账号配置） ─────────────────────────────────────

class GenerateRequest(BaseModel):
    topic_id: str


@router.post("/accounts/{account_id}/generate")
async def generate_from_topic(
    account_id: str,
    req: GenerateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    ai_service: AIService = Depends(get_ai_service)
):
    """
    根据选中的选题 + 账号配置，AI 生成完整图文内容。
    返回 SSE 流：步骤进度 + 提示词逐条扩写 + 完成事件。
    """
    acc = _check_account_owner(account_id, user, db)
    topic = db.query(Topic).filter(
        Topic.id == req.topic_id,
        Topic.account_id == account_id
    ).first()
    if not topic:
        raise HTTPException(status_code=404, detail="选题不存在")

    # 提前读取需要的值，避免 SQLAlchemy lazy-load 跨线程问题
    theme = acc.theme
    target_audience = acc.target_audience
    content_style = acc.content_style or ""
    image_style = acc.image_style or ""
    requirements = list(acc.requirements or [])
    topic_id = topic.id
    topic_title = topic.title
    topic_angle = topic.angle or ""

    async def stream():
        from concurrent.futures import ThreadPoolExecutor
        loop = asyncio.get_running_loop()

        def _send(obj: dict) -> str:
            return f"data: {_json.dumps(obj, ensure_ascii=False)}\n\n"

        # ── Step 0: 分析选题（立即完成）──
        yield _send({"type": "step", "index": 0, "status": "done"})
        yield _send({"type": "step", "index": 1, "status": "running"})

        # ── Step 1: AI 生成文案（~40s）──
        try:
            result = await loop.run_in_executor(None, lambda: ai_service.generate_from_topic(
                theme=theme, target_audience=target_audience,
                content_style=content_style, image_style=image_style,
                requirements=requirements,
                topic_title=topic_title, topic_angle=topic_angle,
            ))
        except Exception as e:
            yield _send({"type": "error", "message": str(e)})
            return

        yield _send({"type": "content", "data": result})
        yield _send({"type": "step", "index": 1, "status": "done"})

        # ── Step 2: 扩写图片提示词（并行，实时流出）──
        image_prompts_raw = result.get("image_prompts", [])
        title_text = result.get("title", "")
        expanded: list = list(image_prompts_raw)

        if ai_service.api_key and image_prompts_raw:
            yield _send({"type": "step", "index": 2, "status": "running"})
            q: asyncio.Queue = asyncio.Queue()

            def _expand(idx: int, prompt: str):
                fb_meta: dict = {}
                try:
                    exp = ai_service.build_image_prompt(prompt, title_text, content_style, image_style, meta=fb_meta)
                except Exception as ex:
                    logger.warning(f"[Expand] 第{idx+1}条扩写失败: {ex}")
                    exp = prompt  # 失败时退回原始描述，绝不让队列卡死
                    fb_meta = {"fallback": True, "reason": "扩写服务异常"}
                loop.call_soon_threadsafe(q.put_nowait, (idx, exp, fb_meta))

            executor = ThreadPoolExecutor(max_workers=3)
            for i, p in enumerate(image_prompts_raw):
                executor.submit(_expand, i, p)
            executor.shutdown(wait=False)

            for _ in range(len(image_prompts_raw)):
                idx, exp, fb_meta = await q.get()
                expanded[idx] = exp
                yield _send({"type": "prompt_expanded", "index": idx, "prompt": exp})
                if fb_meta.get("fallback"):
                    yield _send({
                        "type": "warning",
                        "message": f"第{idx+1}张图提示词扩写失败（{fb_meta.get('reason', '未知原因')}），已退回使用原始简短描述生图，图片细节可能不如预期",
                    })

            yield _send({"type": "step", "index": 2, "status": "done"})

        # ── Step 3: 保存草稿 ──
        yield _send({"type": "step", "index": 3, "status": "running"})

        # 过滤空提示词，避免送空 prompt 给生图接口报 "prompt is empty"
        expanded = [p for p in expanded if p and str(p).strip()][:9]
        imgs_to_gen = expanded
        placeholder_images = [_make_placeholder(p, i) for i, p in enumerate(imgs_to_gen)] \
            or [_make_placeholder("封面图", 0)]

        # 用独立 session 存库（流式响应期间 Depends 的 session 生命周期不可靠）
        from database import SessionLocal
        save_db = SessionLocal()
        content_id = None
        try:
            content_obj = Content(
                id=str(uuid.uuid4()),
                account_id=account_id,
                topic_id=topic_id,
                title=result.get("title", ""),
                content=result.get("content", ""),
                tags=result.get("tags", []),
                images=placeholder_images,
                image_prompts=expanded,
                status=ContentStatus.draft,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            save_db.add(content_obj)
            t = save_db.query(Topic).filter(Topic.id == topic_id).first()
            if t:
                t.status = TopicStatus.used  # type: ignore
            save_db.commit()
            content_id = content_obj.id
        except Exception as e:
            logger.error(f"[Generate] 保存草稿失败: {e}")
            yield _send({"type": "error", "message": f"保存草稿失败：{e}"})
            return
        finally:
            save_db.close()

        # 后台生成真实图片
        image_svc = ImageService()
        if image_svc.available and imgs_to_gen:
            def _bg_gen(cid: str, prompts: list):
                from database import SessionLocal as _SL
                from concurrent.futures import ThreadPoolExecutor as _TPE, as_completed as _ac
                bg_db = _SL()
                try:
                    valid = [(i, p) for i, p in enumerate(prompts) if p and str(p).strip()]
                    results: dict = {}
                    with _TPE(max_workers=min(len(valid), 3)) as pool:
                        futs = {pool.submit(ImageService.for_index(i).generate, p): i
                                for i, p in valid}
                        for fut in _ac(futs):
                            results[futs[fut]] = fut.result()
                    c = bg_db.query(Content).filter(Content.id == cid).first()
                    if c:
                        imgs = list(c.images or [])
                        for idx, url in results.items():
                            if url and idx < len(imgs):
                                imgs[idx] = url
                        c.images = imgs  # type: ignore
                        c.updated_at = datetime.utcnow()  # type: ignore
                        bg_db.commit()
                        logger.info(f"[BG] 内容 {cid[:8]} 图片更新完成")
                except Exception as e:
                    logger.error(f"[BG] 图片生成失败: {e}")
                finally:
                    bg_db.close()

            threading.Thread(target=_bg_gen, args=(content_id, imgs_to_gen), daemon=True).start()

        yield _send({"type": "step", "index": 3, "status": "done"})
        yield _send({
            "type": "done",
            "id": content_id,
            "title": result.get("title", ""),
            "content": result.get("content", ""),
            "tags": result.get("tags", []),
            "images": placeholder_images,
            "image_prompts_cn": expanded,
            "images_generating": image_svc.available and bool(imgs_to_gen),
            "topic": {"id": topic_id, "title": topic_title},
            "content_style": content_style,
            "image_style": image_style,
            "status": "draft",
        })

    return StreamingResponse(stream(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })


# ─── 自动运营（Agent 自动化） ─────────────────────────────────────────────

class AutoConfigRequest(BaseModel):
    auto_enabled: Optional[bool] = None
    auto_frequency: Optional[str] = None   # daily / every_2_days / weekly
    auto_count: Optional[int] = None       # 每次产出篇数 1-5


def _next_run_iso(acc: XiaohongshuAccount) -> Optional[str]:
    from services.auto_agent import FREQUENCY_DAYS
    from datetime import timedelta
    if not acc.auto_enabled:
        return None
    if acc.last_auto_run is None:
        return "尽快"
    days = FREQUENCY_DAYS.get(acc.auto_frequency or "daily", 1)
    return (acc.last_auto_run + timedelta(days=days)).isoformat()


@router.get("/accounts/{account_id}/auto")
def get_auto_config(
    account_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取账号自动运营配置和状态。"""
    acc = _check_account_owner(account_id, user, db)
    return {
        "auto_enabled": bool(acc.auto_enabled),
        "auto_frequency": acc.auto_frequency or "daily",
        "auto_count": int(acc.auto_count or "1"),
        "last_auto_run": acc.last_auto_run.isoformat() if acc.last_auto_run else None,
        "next_run": _next_run_iso(acc),
    }


@router.put("/accounts/{account_id}/auto")
def update_auto_config(
    account_id: str,
    req: AutoConfigRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """更新自动运营配置。"""
    acc = _check_account_owner(account_id, user, db)

    # 开启自动运营前，校验账号已配置主题或关键词
    if req.auto_enabled and not (acc.theme or acc.keywords):
        raise HTTPException(
            status_code=400,
            detail="请先在「配置」中设定账号主题或关键词，再开启自动运营"
        )

    if req.auto_enabled is not None:
        acc.auto_enabled = req.auto_enabled  # type: ignore
    if req.auto_frequency is not None:
        if req.auto_frequency not in ("daily", "every_2_days", "weekly"):
            raise HTTPException(status_code=400, detail="无效的频率")
        acc.auto_frequency = req.auto_frequency  # type: ignore
    if req.auto_count is not None:
        acc.auto_count = str(max(1, min(req.auto_count, 5)))  # type: ignore
    acc.updated_at = datetime.utcnow()  # type: ignore
    db.commit()
    db.refresh(acc)

    return {
        "auto_enabled": bool(acc.auto_enabled),
        "auto_frequency": acc.auto_frequency,
        "auto_count": int(acc.auto_count or "1"),
        "last_auto_run": acc.last_auto_run.isoformat() if acc.last_auto_run else None,
        "next_run": _next_run_iso(acc),
    }


@router.post("/accounts/{account_id}/auto/run")
def run_auto_now(
    account_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    ai_service: AIService = Depends(get_ai_service)
):
    """立即手动触发一次自动产出（不影响定时计划）。"""
    acc = _check_account_owner(account_id, user, db)
    from services.auto_agent import run_account_once
    result = run_account_once(acc, db, ai_service)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "产出失败"))
    return result


# ─── 账号内容列表 ─────────────────────────────────────────────────────────

@router.get("/accounts/{account_id}/contents")
def list_account_contents(
    account_id: str,
    status: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取某账号下的所有内容草稿/已发布。"""
    _check_account_owner(account_id, user, db)
    q = db.query(Content).filter(Content.account_id == account_id)
    if status:
        try:
            q = q.filter(Content.status == ContentStatus(status))
        except ValueError:
            pass
    contents = q.order_by(Content.created_at.desc()).limit(50).all()
    return {"contents": [
        {
            "id": c.id,
            "title": c.title,
            "content": c.content,
            "tags": c.tags,
            "images": c.images,
            "image_prompts": c.image_prompts or [],
            "status": c.status.value,
            "image_status": c.image_status or "none",
            "quality_score": c.quality_score,
            "needs_review": bool(c.needs_review),
            "topic_id": c.topic_id,
            "created_at": c.created_at.isoformat(),
        }
        for c in contents
    ]}


# ─── 后台任务进度 ─────────────────────────────────────────────────────────────

# 内容创作 Agent 的典型步数（查历史→搜热点→生成→质检→存稿），用于估算进度
_EXPECTED_AGENT_STEPS = 5


@router.get("/jobs")
def list_active_jobs(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """当前用户所有进行中的后台任务，供全局进度条轮询。

    覆盖两类耗时操作：
    - 内容创作：AgentRun 处于 running
    - 配图生成：Content.image_status 为 pending（后台线程逐张回写）
    """
    from models import AgentRun, AgentRunStatus

    account_rows = db.query(
        XiaohongshuAccount.id, XiaohongshuAccount.username, XiaohongshuAccount.theme
    ).filter(XiaohongshuAccount.user_id == user.id).all()

    names = {r.id: (r.theme or r.username or "账号") for r in account_rows}
    account_ids = list(names)
    now = datetime.utcnow()
    jobs = []

    # 内容创作
    runs = (
        db.query(AgentRun)
        .filter(AgentRun.account_id.in_(account_ids),
                AgentRun.status == AgentRunStatus.running)
        .order_by(AgentRun.started_at.desc())
        .limit(20)
        .all()
    ) if account_ids else []
    for r in runs:
        done_steps = len(r.steps or [])
        elapsed = int((now - r.started_at).total_seconds()) if r.started_at else 0
        # 卡死超过 30 分钟的不再展示，避免进度条永久悬着
        if elapsed > 1800:
            continue
        jobs.append({
            "id":           r.id,
            "kind":         "content",
            "label":        f"正在创作内容 · {names.get(r.account_id, '账号')}",
            "account_id":   r.account_id,
            "progress":     min(0.95, done_steps / _EXPECTED_AGENT_STEPS) if done_steps else 0.05,
            "detail":       f"第 {done_steps} 步",
            "elapsed_sec":  elapsed,
        })

    # 配图生成：按已产出的真实图片数算真进度。
    # 归属要走两条路径——创建页新建的独立草稿只有 user_id，没有 account_id
    from sqlalchemy import or_
    owner_cond = [Content.user_id == user.id]
    if account_ids:
        owner_cond.append(Content.account_id.in_(account_ids))
    pending = (
        db.query(Content)
        .filter(or_(*owner_cond), Content.image_status == "pending")
        .order_by(Content.updated_at.desc())
        .limit(20)
        .all()
    )
    for c in pending:
        total = len(c.image_prompts or []) or len(c.images or []) or 1
        done  = len([u for u in (c.images or []) if u and "/uploads/" in u])
        # 用 updated_at 而非 created_at：草稿可能很早就建了，之后才重新生成配图。
        # 按 created_at 算的话老草稿一开工就超阈值被过滤掉，进度条永远不显示。
        # updated_at 每张落库都会推进，所以"多久没动"正是判断卡死的正确信号。
        idle = int((now - c.updated_at).total_seconds()) if c.updated_at else 0
        if idle > 900:
            # 15 分钟没有任何进展 = 任务已经死了（进程重启、客户端断开等）。
            # 不能只是隐藏：状态留在 pending 会让这条草稿永远显示"生成中"。
            # 直接按现有图片修正状态，自愈掉。
            imgs_all = list(c.images or [])
            real_all = len([u for u in imgs_all if u and "/uploads/" in u])
            c.image_status = ("done" if real_all and real_all >= total
                              else "partial" if real_all else "failed")
            db.commit()
            continue
        # 已有图片数就够了却仍在 pending = 单张重新生成。
        # 这种情况下"已完成/总数"不会变化，按比例算会卡在同一个百分比，
        # 看起来像死住了；改为不确定态，由前端跑滚动条。
        regenerating = done >= total
        jobs.append({
            "id":            f"img-{c.id}",
            "kind":          "image",
            "label":         (f"正在重新生成配图 · {(c.title or '未命名')[:16]}"
                              if regenerating else
                              f"正在生成配图 · {(c.title or '未命名')[:16]}"),
            "account_id":    c.account_id,
            "content_id":    c.id,
            "progress":      None if regenerating else (done / total if total else 0),
            "indeterminate": regenerating,
            "detail":        "重新生成中" if regenerating else f"{done}/{total} 张",
            "idle_sec":      idle,
        })

    return {"jobs": jobs, "active": len(jobs)}


@router.get("/accounts/{account_id}/runs")
def list_agent_runs(
    account_id: str,
    limit: int = 20,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """账号的 Agent 运行历史（步骤/评分/token/耗时），用于复盘与成本核查。"""
    from models import AgentRun

    _check_account_owner(account_id, user, db)
    rows = (
        db.query(AgentRun)
        .filter(AgentRun.account_id == account_id)
        .order_by(AgentRun.started_at.desc())
        .limit(min(limit, 100))
        .all()
    )
    return {"runs": [
        {
            "id":          r.id,
            "trigger":     r.trigger,
            "status":      r.status.value if r.status else None,
            "step_count":  r.step_count,
            "score":       r.score,
            "content_id":  r.content_id,
            "token_usage": r.token_usage,
            "duration_ms": r.duration_ms,
            "error":       r.error,
            "started_at":  r.started_at.isoformat() if r.started_at else None,
        }
        for r in rows
    ]}
