"""
Agent 路由

POST /api/agent/chat/{account_id}
  → 账号管家对话（理解需求→改配置→可触发内容创作），SSE 流式推送

POST /api/agent/run/{account_id}
  → 为账号运行一次完整 ReAct Agent 内容创作
  → SSE 流式推送每一步进度
"""

import asyncio
import json
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from database import get_db
from models import User, XiaohongshuAccount
from dependencies import get_current_user, get_ai_service
from services.ai_service import AIService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/agent", tags=["agent"])


# ─── 账号管家：对话式 Agent SSE ──────────────────────────────────────────────

@router.post("/chat/{account_id}")
async def manager_chat(
    account_id: str,
    request: dict,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    ai_service: AIService = Depends(get_ai_service),
):
    """
    账号管家对话。Agent 在对话中直接读写账号配置、触发内容创作。
    SSE 推送：tool_call / tool_result / profile_updated / agent_progress / assistant_message
    """
    message = (request.get("message") or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="消息不能为空")

    account = db.query(XiaohongshuAccount).filter(
        XiaohongshuAccount.id == account_id,
        XiaohongshuAccount.user_id == user.id,
    ).first()
    if not account:
        raise HTTPException(status_code=404, detail="账号不存在或无权限")

    from services.agent.manager import ManagerAgent
    from database import SessionLocal
    from models import AccountConversation, MessageRole

    loop: asyncio.AbstractEventLoop = asyncio.get_running_loop()
    q: asyncio.Queue = asyncio.Queue()

    def on_event(event: dict) -> None:
        loop.call_soon_threadsafe(q.put_nowait, event)

    def run_sync() -> None:
        chat_db = SessionLocal()
        try:
            chat_account = chat_db.query(XiaohongshuAccount).filter(
                XiaohongshuAccount.id == account_id
            ).first()
            agent = ManagerAgent(db=chat_db, ai_service=ai_service)
            reply = agent.chat(account=chat_account, user_message=message, on_event=on_event)

            # 持久化对话（在 Agent 跑完后一并写入，保证历史顺序正确）
            chat_db.add(AccountConversation(
                id=str(uuid.uuid4()), account_id=account_id,
                role=MessageRole.user, message=message,
            ))
            chat_db.add(AccountConversation(
                id=str(uuid.uuid4()), account_id=account_id,
                role=MessageRole.assistant, message=reply,
            ))
            chat_db.commit()

            on_event({"type": "assistant_message", "content": reply})
        except Exception as e:
            logger.error(f"[AgentRouter] manager_chat 异常: {e}")
            on_event({"type": "error", "message": str(e)})
        finally:
            chat_db.close()
            loop.call_soon_threadsafe(q.put_nowait, None)

    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="manager")
    executor.submit(run_sync)
    executor.shutdown(wait=False)

    async def event_stream():
        while True:
            event = await q.get()
            if event is None:
                break
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ─── 新版：ReAct Agent SSE ────────────────────────────────────────────────────

@router.post("/run/{account_id}")
async def run_agent(
    account_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    ai_service: AIService = Depends(get_ai_service),
):
    """
    为账号运行一次完整 ReAct Agent 内容创作。
    通过 SSE 实时推送每一步的工具调用和结果。
    """
    # 验证账号归属
    account = db.query(XiaohongshuAccount).filter(
        XiaohongshuAccount.id == account_id,
        XiaohongshuAccount.user_id == user.id,
    ).first()
    if not account:
        raise HTTPException(status_code=404, detail="账号不存在或无权限")

    from services.agent.core import AgentRunner
    from database import SessionLocal

    loop: asyncio.AbstractEventLoop = asyncio.get_running_loop()
    q: asyncio.Queue = asyncio.Queue()

    def on_event(event: dict) -> None:
        loop.call_soon_threadsafe(q.put_nowait, event)

    def run_sync() -> None:
        """在线程池中同步运行 Agent，完成后发哨兵 None。"""
        agent_db = SessionLocal()
        try:
            # 在新 session 里重新加载账号，避免跨线程共享 ORM 对象
            agent_account = agent_db.query(XiaohongshuAccount).filter(
                XiaohongshuAccount.id == account_id
            ).first()
            runner = AgentRunner(db=agent_db, ai_service=ai_service)
            runner.run(account=agent_account, on_event=on_event, trigger="manual")
        except Exception as e:
            logger.error(f"[AgentRouter] run_sync 异常: {e}")
            on_event({"type": "error", "message": str(e)})
        finally:
            agent_db.close()
            loop.call_soon_threadsafe(q.put_nowait, None)  # 哨兵，通知 SSE 结束

    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="agent")
    executor.submit(run_sync)
    executor.shutdown(wait=False)

    async def event_stream():
        while True:
            event = await q.get()
            if event is None:
                break
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
