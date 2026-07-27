"""Celery 任务入口：读取已提交任务，执行 LangGraph，并保存图的结果。"""

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi.encoders import jsonable_encoder

from app.core.celery_app import celery_app

from app.db.session import SessionLocal
from app.models.analysis_task import AnalysisTask, AnalysisTaskDocument
from app.models.company import BusinessDataSource, SchemaSnapshot
from app.repositories.conversation_repository import (
    get_assistant_message_by_task_id,
    touch_conversation,
)
from app.services.workflow_graph import run_analysis
from app.schemas.final_analysis import FinalAnalysisReport

# 导入所有模型确保 SQLAlchemy 能解析外键
from app.models.document_chunk import DocumentChunk  # noqa: F401
from app.models.documents import Documents  # noqa: F401
from app.models.conversation import Conversation, ConversationMessage  # noqa: F401
from app.models.user import User  # noqa: F401

logger = logging.getLogger(__name__)
TERMINAL_TASK_STATUSES = {"completed", "partial", "failed", "cancelled"}
GENERIC_WORKER_FAILURE_MESSAGE = "分析任务执行失败，请稍后重试。"
RETRYING_WORKER_MESSAGE = "分析服务暂时不可用，正在自动重试。"


class RetryableAnalysisTaskError(Exception):
    """A dependency failed transiently and the whole analysis can be retried."""


def _is_retryable_exception(exc: Exception) -> bool:
    return isinstance(exc, (ConnectionError, TimeoutError, OSError))


def _duration_ms(record: AnalysisTask) -> int | None:
    started_at = getattr(record, "started_at", None)
    if started_at is None:
        return None
    return max(
        0,
        round((datetime.now(timezone.utc) - started_at).total_seconds() * 1000),
    )


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
    if record.conversation_id is not None:
        touch_conversation(db, conversation_id=record.conversation_id)


def _stop_if_cancelled(db, record: AnalysisTask) -> bool:
    """在每次不可逆操作前，以 Worker 自己的 Session 重新确认取消状态。"""
    db.refresh(record)
    if record.status != "cancelled":
        return False

    record.completed_at = datetime.now(timezone.utc)
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


def _update_stage(db, record: AnalysisTask, stage: str) -> None:
    """Persist a frontend-visible workflow stage before entering that node."""
    db.refresh(record)
    if record.status == "cancelled":
        return
    record.stage = stage
    db.commit()


def _claim_task(db, *, task_id: int, celery_task_id: str | None) -> AnalysisTask | None:
    """Atomically move only queued/retrying work into the running state."""
    now = datetime.now(timezone.utc)
    claimed = (
        db.query(AnalysisTask)
        .filter(
            AnalysisTask.id == task_id,
            AnalysisTask.status.in_(("queued", "retrying")),
        )
        .update(
            {
                AnalysisTask.status: "running",
                AnalysisTask.stage: "planning",
                AnalysisTask.started_at: now,
                AnalysisTask.celery_task_id: celery_task_id,
                AnalysisTask.error_message: None,
                AnalysisTask.error_type: None,
                AnalysisTask.attempt_count: AnalysisTask.attempt_count + 1,
            },
            synchronize_session=False,
        )
    )
    db.commit()
    return db.get(AnalysisTask, task_id) if claimed else None


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
    raw_report = review_result.get("report")
    report = (
        FinalAnalysisReport.model_validate(raw_report)
        if isinstance(raw_report, dict)
        else None
    )
    report_status = report.status if report is not None else None
    is_failed = is_failed or report_status == "failed"
    is_partial = (
        review_result.get("review_status") == "partial" or report_status == "partial"
    )

    record.stage = "saving_result"
    db.commit()
    if _stop_if_cancelled(db, record):
        return

    record.result_summary = final_answer
    record.result_data = jsonable_encoder(
        {
            "type": "langgraph_workflow",
            "answer": final_answer,
            "plan": workflow_result.get("plan"),
            "planner_result": workflow_result.get("planner_result"),
            "terminal_result": terminal_result,
            "data_result": workflow_result.get("data_result"),
            "knowledge_result": workflow_result.get("knowledge_result"),
            "review_result": workflow_result.get("review_result"),
            "report": report.model_dump(mode="json") if report is not None else None,
            "execution": {
                "external_retry_count": workflow_result.get("external_retry_count", 0),
                "max_external_retries": workflow_result.get("max_external_retries", 0),
                "loop_stop_reason": workflow_result.get("loop_stop_reason"),
                "loop_history": workflow_result.get("loop_history", []),
                "scope_fingerprint": workflow_result.get("scope_fingerprint"),
            },
        }
    )

    # ── needs_clarification ─────────────────────────────────
    is_clarification = (terminal_result or {}).get("outcome") == "needs_clarification"
    if is_clarification:
        record.status = "needs_clarification"
        record.clarification_status = "waiting"
        record.clarification_missing_fields = (terminal_result or {}).get(
            "missing_fields"
        )
        record.error_message = None
    elif is_failed or not final_answer:
        record.status = "failed"
        record.error_message = "分析工作流未能生成可返回的结果。"
    elif is_partial:
        record.status = "partial"
        record.error_message = None
    else:
        record.status = "completed"
        record.error_message = None

    # 进入终态时设置 completed_at
    if record.status in TERMINAL_TASK_STATUSES:
        record.completed_at = datetime.now(timezone.utc)
        record.duration_ms = _duration_ms(record)

    _sync_assistant_message(
        db,
        record,
        status=record.status,
        content=final_answer or GENERIC_WORKER_FAILURE_MESSAGE,
    )
    record.stage = "completed"
    db.commit()


@celery_app.task(bind=True, max_retries=3)
def process_analysis_task(self, task_id: int):
    """用独立数据库 Session 执行一次 LangGraph 分析工作流。"""
    db = SessionLocal()
    try:
        record = _claim_task(
            db,
            task_id=task_id,
            celery_task_id=getattr(self.request, "id", None),
        )
        if record is None:
            logger.info("Task %s was already claimed, terminal, or missing", task_id)
            return
        _sync_assistant_message(
            db,
            record,
            status="running",
            content=None,
        )
        db.commit()

        if _stop_if_cancelled(db, record):
            return

        document_ids = [
            row.document_id
            for row in db.query(AnalysisTaskDocument)
            .filter(AnalysisTaskDocument.task_id == record.id)
            .all()
        ]
        workflow_kwargs = {"conversation_context": record.context_snapshot}
        if document_ids:
            workflow_kwargs["document_ids"] = document_ids
        if record.data_source_id is not None and record.schema_snapshot_id is not None:
            source = (
                db.query(BusinessDataSource)
                .filter(BusinessDataSource.id == record.data_source_id)
                .first()
            )
            snapshot = (
                db.query(SchemaSnapshot)
                .filter(SchemaSnapshot.id == record.schema_snapshot_id)
                .first()
            )
            if (
                source is None
                or snapshot is None
                or snapshot.data_source_id != source.id
                or source.company_id != record.company_id
            ):
                raise RuntimeError("Analysis task has an invalid company data context")
            workflow_kwargs["business_data_source"] = source
            workflow_kwargs["schema_catalog"] = snapshot.catalog
        workflow_result = run_analysis(
            record.question,
            record.user_id,
            company_id=record.company_id,
            stage_callback=lambda stage: _update_stage(db, record, stage),
            **workflow_kwargs,
        )

        terminal_result = workflow_result.get("terminal_result") or {}
        if terminal_result.get("retryable"):
            raise RetryableAnalysisTaskError(
                terminal_result.get("error_code") or "retryable_workflow_failure"
            )

        if _stop_if_cancelled(db, record):
            return

        _save_workflow_result(db, record, workflow_result)
        db.refresh(record)
        logger.info("Task %s completed through LangGraph", task_id)

    except RetryableAnalysisTaskError as exc:
        db.rollback()
        db.expire_all()
        record = db.get(AnalysisTask, task_id)
        if record is None or record.status == "cancelled":
            return
        record.error_type = type(exc).__name__
        record.error_message = "分析服务暂时不可用。"
        record.duration_ms = _duration_ms(record)
        if self.request.retries >= self.max_retries:
            record.status = "failed"
            record.completed_at = datetime.now(timezone.utc)
            _sync_assistant_message(
                db,
                record,
                status="failed",
                content=GENERIC_WORKER_FAILURE_MESSAGE,
            )
            db.commit()
            raise

        record.status = "retrying"
        record.stage = "retrying"
        _sync_assistant_message(
            db,
            record,
            status="running",
            content=RETRYING_WORKER_MESSAGE,
        )
        db.commit()
        raise self.retry(exc=exc, countdown=2 ** (self.request.retries + 1))
    except Exception as exc:
        if _is_retryable_exception(exc):
            db.rollback()
            db.expire_all()
            record = db.get(AnalysisTask, task_id)
            if record is None or record.status == "cancelled":
                return
            retry_error = RetryableAnalysisTaskError(str(exc))
            record.error_type = type(exc).__name__
            record.error_message = "分析服务暂时不可用。"
            record.duration_ms = _duration_ms(record)
            if self.request.retries < self.max_retries:
                record.status = "retrying"
                record.stage = "retrying"
                _sync_assistant_message(
                    db,
                    record,
                    status="running",
                    content=RETRYING_WORKER_MESSAGE,
                )
                db.commit()
                raise self.retry(
                    exc=retry_error, countdown=2 ** (self.request.retries + 1)
                )

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
        record.completed_at = datetime.now(timezone.utc)
        record.duration_ms = _duration_ms(record)
        record.error_type = type(exc).__name__
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
