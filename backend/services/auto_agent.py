"""
Agent 自动运营核心逻辑

每个开启自动运营的账号，定时执行内容创作。

实际创作交给 services.agent.core.AgentRunner（ReAct Agent）执行，
和用户在工作台手动点「立即创作」、以及管家 Agent 的 create_post 工具走**同一条**路径，
因此自动产出同样享有：
  - get_account_history 选题去重
  - evaluate_content 质量评分与低分重试
  - save_draft 触发的后台真实配图

被调度器（定时）和 API（立即运行一次）共用。
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List

from sqlalchemy.orm import Session

from models import XiaohongshuAccount
from services.ai_service import AIService

logger = logging.getLogger(__name__)

# 频率 → 间隔天数
FREQUENCY_DAYS = {
    "daily": 1,
    "every_2_days": 2,
    "weekly": 7,
}


def should_run(account: XiaohongshuAccount) -> bool:
    """判断账号是否到了该自动产出的时间。"""
    if not account.auto_enabled:
        return False
    if account.last_auto_run is None:
        return True  # 从未运行过，立即跑
    interval_days = FREQUENCY_DAYS.get(account.auto_frequency or "daily", 1)
    next_run = account.last_auto_run + timedelta(days=interval_days)
    return datetime.utcnow() >= next_run


def run_account_once(
    account: XiaohongshuAccount,
    db: Session,
    ai_service: AIService,
    count: int = None,
) -> Dict[str, Any]:
    """
    为一个账号执行一次自动产出，产出 count 篇（每篇一次完整 Agent 流程）。
    返回 {"success": bool, "produced": int, "contents": [...], "error": str}
    """
    from services.agent.core import AgentRunner

    if count is None:
        try:
            count = int(account.auto_count or "1")
        except (ValueError, TypeError):
            count = 1
    count = max(1, min(count, 5))  # 限制 1-5 篇

    if not account.theme and not account.keywords:
        return {"success": False, "produced": 0, "contents": [],
                "error": "账号未设定主题或关键词，无法自动选题"}

    produced_contents: List[Dict[str, Any]] = []
    errors: List[str] = []

    for i in range(count):
        # 收集本篇的关键事件，便于排查（自动运营没有 SSE 消费者）
        events: Dict[str, Any] = {}

        def on_event(ev: dict) -> None:
            etype = ev.get("type")
            if etype == "evaluation":
                events["score"]   = ev.get("score")
                events["verdict"] = ev.get("verdict")
            elif etype in ("warning", "error"):
                logger.warning(
                    f"[AutoAgent] 账号 {account.id} 第 {i + 1} 篇 {etype}: "
                    f"{ev.get('message', '')}"
                )

        # 每篇一个全新 runner：草稿暂存区与 token 计数不跨篇累积
        # strict_quality：自动运营无人值守，质检服务失败时不允许按默认分放行
        runner = AgentRunner(db=db, ai_service=ai_service, strict_quality=True)
        try:
            result = runner.run(account=account, on_event=on_event, trigger="auto")
        except Exception as e:
            logger.error(f"[AutoAgent] 账号 {account.id} 第 {i + 1} 篇 Agent 异常: {e}")
            errors.append(str(e))
            continue

        if result.get("success"):
            produced_contents.append({
                "id":    result.get("content_id"),
                "title": result.get("title"),
                "score": events.get("score"),
            })
        else:
            err = result.get("error", "未知错误")
            logger.error(f"[AutoAgent] 账号 {account.id} 第 {i + 1} 篇失败: {err}")
            errors.append(err)

    # 更新 last_auto_run —— 无论成功与否都推进，避免失败账号被每轮反复重试
    account.last_auto_run = datetime.utcnow()
    db.commit()

    logger.info(
        f"[AutoAgent] 账号 {account.id}({account.username}) "
        f"自动产出 {len(produced_contents)}/{count} 篇"
    )
    return {
        "success":  len(produced_contents) > 0,
        "produced": len(produced_contents),
        "contents": produced_contents,
        "error":    None if produced_contents else "; ".join(errors) or "未产出任何内容",
    }


def run_all_due_accounts(db: Session, ai_service: AIService) -> Dict[str, Any]:
    """
    扫描所有开启自动运营、且到点的账号，逐个执行产出。
    供调度器定时调用。
    """
    accounts = db.query(XiaohongshuAccount).filter(
        XiaohongshuAccount.auto_enabled == True  # noqa: E712
    ).all()

    ran = []
    for account in accounts:
        if should_run(account):
            # 先取出用户名：异常分支里会 rollback，之后 ORM 实例已过期，
            # 再读属性会触发重新查询（失败时可能直接抛 ObjectDeletedError）
            username = account.username
            logger.info(f"[AutoAgent] 触发账号 {username} 自动产出")
            try:
                result = run_account_once(account, db, ai_service)
            except Exception as e:
                # 单个账号出错不能中断整轮调度
                logger.error(f"[AutoAgent] 账号 {username} 执行异常: {e}")
                db.rollback()
                result = {"success": False, "produced": 0, "contents": [], "error": str(e)}
            ran.append({"account": username, **result})

    return {"checked": len(accounts), "ran": len(ran), "details": ran}
