"""Celery 任务入口：读取已提交任务，执行 LangGraph，并保存图的结果。"""

import logging
from typing import Any

from app.core.celery_app import celery_app

from app.db.session import SessionLocal
from app.models.analysis_task import AnalysisTask
from app.repositories.conversation_repository import (
    get_assistant_message_by_task_id,
    touch_conversation,
)
from app.services.workflow_graph import run_analysis

# 导入所有模型确保 SQLAlchemy 能解析外键
from app.models.document_chunk import DocumentChunk  # noqa: F401
from app.models.documents import Documents  # noqa: F401
from app.models.conversation import Conversation, ConversationMessage  # noqa: F401
from app.models.user import User  # noqa: F401

logger = logging.getLogger(__name__)
TERMINAL_TASK_STATUSES = {"completed", "partial", "failed", "cancelled"}
GENERIC_WORKER_FAILURE_MESSAGE = "分析任务执行失败，请稍后重试。"


def _sync_assistant_message(
    db,
    record: AnalysisTask,
    *,
    status: str,
    content: str | None,
) -> None:
    if getattr(record, "conversation_id", None) is None:
        return
    assistant_message = get_assistant_message_by_task_id(db, task_id=record.id)
    if assistant_message is None:
        return
    assistant_message.status = status
    assistant_message.content = content
    touch_conversation(db, conversation_id=record.conversation_id)


def _stop_if_cancelled(db, record: AnalysisTask) -> bool:
    """在每次不可逆操作前，以 Worker 自己的 Session 重新确认取消状态。"""
    db.refresh(record)
    if record.status != "cancelled":
        return False

    _sync_assistant_message(
        db,
        record,
        status="cancelled",
        content="本次分析已取消。",
    )
    db.commit()

    logger.info(
        "Task cancelled; worker stopped before next stage",
        extra={
            "task_id": record.id,
            "user_id": record.user_id,
            "stage": record.stage,
            "attempt_count": record.attempt_count,
            "reason": "cancelled_by_user",
        },
    )
    return True


def _save_workflow_result(
    db, record: AnalysisTask, workflow_result: dict[str, Any]
) -> None:
    """将 LangGraph 的最终 State 转为当前 AnalysisTask 的可查询结果。

    当前表的 stage 仍是旧 RAG 枚举，因此本轮只在写库时使用现有的
    ``save_result`` 和 ``completed``。后续再单独迁移为 planning、data、
    knowledge、review 等更精确的阶段。
    """
    final_answer = workflow_result.get("final_answer")
    terminal_result = workflow_result.get("terminal_result")
    is_failed = (terminal_result or {}).get("outcome") == "failed"
    review_result = workflow_result.get("review_result") or {}
    is_partial = review_result.get("review_status") == "partial"

    record.stage = "save_result"
    db.commit()
    if _stop_if_cancelled(db, record):
        return

    record.result_summary = final_answer
    record.result_data = {
        "type": "langgraph_workflow",
        "answer": final_answer,
        "plan": workflow_result.get("plan"),
        "planner_result": workflow_result.get("planner_result"),
        "terminal_result": terminal_result,
        "data_result": workflow_result.get("data_result"),
        "knowledge_result": workflow_result.get("knowledge_result"),
        "review_result": workflow_result.get("review_result"),
    }

    if is_failed or not final_answer:
        record.status = "failed"
        record.error_message = "分析工作流未能生成可返回的结果。"
    elif is_partial:
        record.status = "partial"
        record.error_message = None
    else:
        record.status = "completed"
        record.error_message = None

    _sync_assistant_message(
        db,
        record,
        status=record.status,
        content=final_answer or GENERIC_WORKER_FAILURE_MESSAGE,
    )
    record.stage = "completed"
    db.commit()


@celery_app.task
def process_analysis_task(task_id: int):
    """用独立数据库 Session 执行一次 LangGraph 分析工作流。"""
    db = SessionLocal()
    try:
        record = db.query(AnalysisTask).filter(AnalysisTask.id == task_id).first()
        if record is None:
            logger.error("Task %s not found", task_id)
            return
        if record.status in TERMINAL_TASK_STATUSES:
            logger.info(
                "Task %s already terminal with status %s", task_id, record.status
            )
            return

        record.attempt_count += 1
        record.status = "running"
        _sync_assistant_message(
            db,
            record,
            status="running",
            content=None,
        )
        # 旧表尚无 planning；这里表示 Worker 已进入包含 Planner 的工作流。
        record.stage = "call_model"
        db.commit()

        if _stop_if_cancelled(db, record):
            return

        workflow_result = run_analysis(
            record.question,
            record.user_id,
            conversation_context=record.context_snapshot,
        )

        if _stop_if_cancelled(db, record):
            return

        _save_workflow_result(db, record, workflow_result)
        db.refresh(record)
        logger.info("Task %s completed through LangGraph", task_id)

    except Exception:
        db.rollback()
        db.expire_all()
        logger.exception("Task %s failed without retry", task_id)

        record = db.query(AnalysisTask).filter(AnalysisTask.id == task_id).first()
        if record is None:
            logger.error("Task %s disappeared while handling an error", task_id)
            raise
        if record.status == "cancelled":
            logger.info("Task %s was cancelled while handling an error", task_id)
            return

        record.status = "failed"
        record.error_message = "分析任务执行失败。"
        _sync_assistant_message(
            db,
            record,
            status="failed",
            content=GENERIC_WORKER_FAILURE_MESSAGE,
        )
        db.commit()
        raise
    finally:
        db.close()
