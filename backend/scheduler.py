"""
Agent 自动运营调度器

每隔固定间隔扫描所有开启自动运营的账号，到点的执行产出。
集成在 FastAPI 启动时启动。
"""
import os
import logging
from apscheduler.schedulers.background import BackgroundScheduler

from database import SessionLocal
from services.ai_service import AIService
from services.auto_agent import run_all_due_accounts

logger = logging.getLogger(__name__)

# 检查间隔（分钟）。每隔这么久扫一次到点的账号。
CHECK_INTERVAL_MINUTES = int(os.getenv("AUTO_AGENT_CHECK_INTERVAL", "30"))

_scheduler: BackgroundScheduler | None = None


def _tick():
    """调度器每次触发：扫描并执行到点的账号。"""
    db = SessionLocal()
    try:
        ai_service = AIService()
        result = run_all_due_accounts(db, ai_service)
        if result["ran"] > 0:
            logger.info(f"[Scheduler] 本轮执行 {result['ran']}/{result['checked']} 个账号")
    except Exception as e:
        logger.error(f"[Scheduler] 执行出错: {e}")
    finally:
        db.close()


def start_scheduler():
    """启动后台调度器。"""
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
    _scheduler.add_job(
        _tick,
        trigger="interval",
        minutes=CHECK_INTERVAL_MINUTES,
        id="auto_agent_tick",
        next_run_time=None,  # 不在启动瞬间跑，等第一个间隔
        max_instances=1,
        coalesce=True,
    )
    _scheduler.start()
    logger.info(f"[Scheduler] 已启动，每 {CHECK_INTERVAL_MINUTES} 分钟检查一次自动运营账号")


def stop_scheduler():
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
