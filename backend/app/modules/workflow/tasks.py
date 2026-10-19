"""Celery 任务入口：读取已提交任务，执行 LangGraph，并保存图的结果。"""

import errno
import logging
import re
from contextlib import contextmanager
from threading import Event, Thread
from typing import Any

from app.core.celery_app import celery_app
from app.core.exceptions import RetryableModelError
from app.core.logging import request_id_context
from app.core.settings import get_settings
from app.db.clock import database_now
from app.db.session import SessionLocal, set_tenant_scope
from app.modules.conversations.models import (  # noqa: F401
    Conversation,
    ConversationMessage,
)
from app.modules.conversations.repository import (
    get_assistant_message_by_task_id,
    touch_conversation,
)

# 导入所有模型确保 SQLAlchemy 能解析外键
from app.modules.documents.chunks import DocumentChunk
from app.modules.documents.models import Documents  # noqa: F401
from app.modules.evaluation.result_fingerprint import (
    result_fingerprint_from_data_result,
    revenue_month_comparison_fingerprint_from_data_result,
)
from app.modules.identity.models import User  # noqa: F401
from app.modules.input_artifacts.attachment_context import (
    build_task_attachment_context,
)
from app.modules.input_artifacts.processing_storage import (
    get_artifact_processing_storage,
)
from app.modules.memory.service import persist_report_memory, select_planner_memories
from app.modules.organizations.models import BusinessDataSource, SchemaSnapshot
from app.modules.reporting.validation import validate_report
from app.modules.reviews.service import create_review_request
from app.modules.runtime.model_governance import ModelBudgetExceeded, model_call_scope
from app.modules.runtime.tool_runtime import ToolRuntime, ToolRuntimeContext
from app.modules.workflow.events import append_workflow_event
from app.modules.workflow.execution import (
    ClaimedExecution,
    checkpoint_stage,
    checkpoint_workflow_state,
    claim_execution,
    execution_heartbeat_interval_seconds,
    finish_execution,
    renew_execution_lease,
    retry_resume_node,
    transition_execution,
)
from app.modules.workflow.graph import run_analysis
from app.modules.workflow.models import (
    AnalysisTask,
    AnalysisTaskDocument,
    AnalysisTaskInputArtifactVersion,
)
from app.modules.workflow.publication import decide_completion
from fastapi.encoders import jsonable_encoder

logger = logging.getLogger(__name__)
TERMINAL_TASK_STATUSES = {"completed", "partial", "failed", "cancelled"}
GENERIC_WORKER_FAILURE_MESSAGE = "分析任务执行失败，请稍后重试。"
RETRYING_WORKER_MESSAGE = "分析服务暂时不可用，正在自动重试。"


def _frozen_allowed_chunk_ids(db, *, task_id: int) -> set[int] | None:
    """Return the persisted scope; an empty scope denies every chunk."""
    if not hasattr(db, "query"):
        return None
    document_ids = [
        row[0]
        for row in (
            db.query(AnalysisTaskDocument.document_id)
            .filter(AnalysisTaskDocument.task_id == task_id)
            .all()
        )
    ]
    return {
        row[0]
        for row in (
            db.query(DocumentChunk.id)
            .filter(DocumentChunk.document_id.in_(document_ids))
            .all()
        )
    }


def _deterministic_validation_result(
    review_result: dict[str, Any], report_validated: bool | None
) -> dict[str, object]:
    """Persist the existing deterministic gate outcomes without inferring missing checks."""
    answer_validation = review_result.get("answer_validation")
    checks = {
        name: answer_validation.get(name)
        if isinstance(answer_validation, dict)
        else None
        for name in ("schema_valid", "numbers_valid", "citations_valid")
    }
    checks["report_validated"] = report_validated
    values = list(checks.values())
    status = "failed" if any(value is False for value in values) else (
        "passed" if all(value is True for value in values) else "unknown"
    )
    return {"status": status, "checks": checks}


def _evaluation_facts(workflow_result: dict[str, Any]) -> dict[str, object]:
    """Persist only structured execution facts that evaluation can later read."""
    plan = workflow_result.get("plan")
    data_result = workflow_result.get("data_result")
    data_result = data_result if isinstance(data_result, dict) else {}
    scope = plan.get("evaluation_scope") if isinstance(plan, dict) else None
    entities = (
        scope.get("entities")
        if isinstance(scope, dict)
        and isinstance(scope.get("entities"), list)
        and scope["entities"]
        and all(isinstance(entity, str) and entity.strip() for entity in scope["entities"])
        else None
    )
    period = (
        scope.get("period")
        if isinstance(scope, dict)
        and isinstance(scope.get("period"), str)
        and scope["period"].strip()
        else None
    )
    data_status = data_result.get("status")
    data_error_code = data_result.get("error_code")
    return {
        "entities": entities,
        "period": period,
        "data_status": (
            data_status
            if data_status in {"ready", "insufficient_evidence", "failed", "not_run"}
            else None
        ),
        "data_error_code": (
            data_error_code
            if isinstance(data_error_code, str)
            and re.fullmatch(r"[a-z0-9_]{1,80}", data_error_code)
            else None
        ),
        "result_fingerprint": result_fingerprint_from_data_result(
            data_result
        ),
        "semantic_result_fingerprint": revenue_month_comparison_fingerprint_from_data_result(
            data_result, period=period
        ),
    }


class RetryableAnalysisTaskError(Exception):
    """A dependency failed transiently and the whole analysis can be retried."""


def _is_retryable_exception(exc: Exception) -> bool:
    if isinstance(exc, OSError) and exc.errno == errno.ENOSPC:
        return False
    return isinstance(
        exc,
        (ConnectionError, TimeoutError, OSError, RetryableModelError),
    )


def _duration_ms(db, record: AnalysisTask) -> int | None:
    started_at = getattr(record, "started_at", None)
    if started_at is None:
        return None
    return max(
        0,
        round((database_now(db) - started_at).total_seconds() * 1000),
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

    record.completed_at = database_now(db)
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


def _update_stage(
    db,
    record: AnalysisTask,
    execution: ClaimedExecution,
    stage: str,
    node_name: str | None = None,
) -> None:
    """Persist a frontend-visible workflow stage before entering that node."""
    db.refresh(record)
    if record.status == "cancelled":
        return
    if checkpoint_stage(
        db,
        attempt=execution.attempt,
        stage=stage,
        completed_node=node_name,
    ):
        append_workflow_event(
            db,
            attempt=execution.attempt,
            company_id=record.company_id,
            event_type="stage_started",
            node_name=node_name or stage,
            status="running",
            details={"stage": stage},
        )
        db.commit()


_NODE_STAGE = {
    "planner_node": "planning",
    "planner_semantic_review_node": "planning",
    "planner_terminal_node": "planning",
    "planning_failure_node": "planning",
    "data_node": "querying_data",
    "knowledge_node": "retrieving_knowledge",
    "reviewer_node": "composing_report",
    "smart_router_node": "composing_report",
}


def _checkpoint_workflow_node(
    db,
    record: AnalysisTask,
    execution: ClaimedExecution,
    completed_node: str,
    next_node: str | None,
    state_patch: dict,
) -> None:
    """Store only JSON-safe node output while the claimed execution owns it."""
    if not checkpoint_workflow_state(
        db,
        attempt=execution.attempt,
        stage=_NODE_STAGE.get(completed_node, "planning"),
        completed_node=completed_node,
        next_node=next_node,
        workflow_state=jsonable_encoder(state_patch),
    ):
        logger.info(
            "Task %s execution lost ownership after %s", record.id, completed_node
        )
        return
    append_workflow_event(
        db,
        attempt=execution.attempt,
        company_id=record.company_id,
        event_type="node_completed",
        node_name=completed_node,
        status="succeeded",
        details={"next_node": next_node},
    )
    db.commit()


def _claim_task(
    db, *, task_id: int, celery_task_id: str | None, worker_id: str | None
) -> ClaimedExecution | None:
    return claim_execution(
        db,
        task_id=task_id,
        celery_task_id=celery_task_id,
        worker_id=worker_id,
    )


@contextmanager
def _maintain_execution_lease(execution: ClaimedExecution):
    """Keep a blocking workflow alive without sharing its SQLAlchemy Session."""
    stop = Event()
    task_id = execution.attempt.task_id
    execution_id = execution.attempt.execution_id

    def heartbeat() -> None:
        interval_seconds = execution_heartbeat_interval_seconds()
        while not stop.wait(interval_seconds):
            heartbeat_db = SessionLocal()
            try:
                if not renew_execution_lease(
                    heartbeat_db,
                    task_id=task_id,
                    execution_id=execution_id,
                ):
                    return
            except Exception:
                heartbeat_db.rollback()
                logger.warning(
                    "Task %s execution heartbeat failed", task_id, exc_info=True
                )
            finally:
                heartbeat_db.close()

    thread = Thread(target=heartbeat, name=f"execution-heartbeat-{task_id}", daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=1)
        if thread.is_alive():
            logger.warning("Task %s execution heartbeat did not stop promptly", task_id)


def _save_workflow_result(
    db,
    record: AnalysisTask,
    execution: ClaimedExecution,
    workflow_result: dict[str, Any],
) -> None:
    """将 LangGraph 的最终 State 转为当前 AnalysisTask 的可查询结果。

    当前表的 stage 仍是旧 RAG 枚举，因此本轮只在写库时使用现有的
    ``save_result`` 和 ``completed``。后续再单独迁移为 planning、data、
    knowledge、review 等更精确的阶段。
    """
    final_answer = workflow_result.get("final_answer")
    terminal_result = workflow_result.get("terminal_result")
    review_result = workflow_result.get("review_result") or {}
    raw_report = review_result.get("report")
    allowed_chunk_ids = _frozen_allowed_chunk_ids(db, task_id=record.id)
    report = (
        validate_report(raw_report, allowed_chunk_ids=allowed_chunk_ids)
        if isinstance(raw_report, dict)
        else None
    )
    deterministic_validation = (
        _deterministic_validation_result(review_result, report is not None)
        if report is not None or isinstance(review_result.get("answer_validation"), dict)
        else None
    )

    if not checkpoint_stage(db, attempt=execution.attempt, stage="saving_result"):
        logger.info("Task %s execution lost ownership before saving", record.id)
        return
    if _stop_if_cancelled(db, record):
        return

    result_data = jsonable_encoder(
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
            "evaluation_facts": _evaluation_facts(workflow_result),
            "execution": {
                "external_retry_count": workflow_result.get("external_retry_count", 0),
                "max_external_retries": workflow_result.get("max_external_retries", 0),
                "loop_stop_reason": workflow_result.get("loop_stop_reason"),
                "loop_history": workflow_result.get("loop_history", []),
                "scope_fingerprint": workflow_result.get("scope_fingerprint"),
            },
        }
    )
    if deterministic_validation is not None:
        result_data["deterministic_validation"] = deterministic_validation

    decision = decide_completion(
        final_answer=final_answer,
        terminal_outcome=(terminal_result or {}).get("outcome"),
        review_status=review_result.get("review_status"),
        report=report,
        company_id=getattr(record, "company_id", None),
    )
    task_status = decision.task_status
    attempt_status = decision.attempt_status
    result_data["publication"] = decision.publication_record()
    error_message = (
        "分析工作流未能生成可返回的结果。" if task_status == "failed" else None
    )
    if decision.report_location == "report_draft":
        # A causal hypothesis may be evidence-supported but is still not a
        # business fact. Keep it as a draft until a company admin approves it.
        task_status = "awaiting_review"
        error_message = None
        result_data["report_draft"] = result_data.pop("report")
        result_data["review"] = {
            "status": "pending",
            "reason_code": "causal_hypothesis_requires_human_review",
        }
    if task_status == "awaiting_review":
        create_review_request(db, task=record)
    if not finish_execution(
        db,
        attempt=execution.attempt,
        task_status=task_status,
        attempt_status=attempt_status,
        result_summary=final_answer,
        result_data=result_data,
        error_message=error_message,
    ):
        logger.info("Task %s execution lost ownership before final publish", record.id)
        return
    db.refresh(record)
    if report is not None and task_status in {"completed", "partial"}:
        persist_report_memory(db, task=record, report=report)
    if task_status == "needs_clarification":
        record.clarification_status = "waiting"
        record.clarification_missing_fields = (terminal_result or {}).get(
            "missing_fields"
        )
    record.duration_ms = _duration_ms(db, record)

    _sync_assistant_message(
        db,
        record,
        status=task_status,
        content=final_answer or GENERIC_WORKER_FAILURE_MESSAGE,
    )
    db.commit()


def _publish_approved_draft(
    db, record: AnalysisTask, execution: ClaimedExecution
) -> None:
    """Publish a pre-validated draft only after a separately audited approval."""
    result_data = dict(record.result_data or {})
    draft = result_data.get("report_draft")
    if draft is None:
        raise ValueError("approved review task is missing its report draft")
    allowed_chunk_ids = _frozen_allowed_chunk_ids(db, task_id=record.id)
    report = validate_report(draft, allowed_chunk_ids=allowed_chunk_ids)
    if report.status != "completed":
        raise ValueError("approved review draft is not a completed report")
    result_data.pop("review_publish_only", None)
    result_data.pop("report_draft", None)
    result_data["report"] = report.model_dump(mode="json")
    result_data["review"] = {"status": "approved"}
    result_data["publication"] = {
        "decision": "published",
        "report_location": "report",
        "reason_code": "human_review_approved",
    }
    summary = result_data.get("answer") or report.executive_summary
    if not finish_execution(
        db,
        attempt=execution.attempt,
        task_status="completed",
        attempt_status="completed",
        result_summary=summary,
        result_data=result_data,
        error_message=None,
    ):
        logger.info(
            "Task %s execution lost ownership before approved publish", record.id
        )
        return
    db.refresh(record)
    persist_report_memory(db, task=record, report=report)
    record.duration_ms = _duration_ms(db, record)
    _sync_assistant_message(db, record, status="completed", content=summary)
    db.commit()


@celery_app.task(bind=True, max_retries=3)
def process_analysis_task(self, task_id: int):
    """用独立数据库 Session 执行一次 LangGraph 分析工作流。"""
    db = SessionLocal()
    execution: ClaimedExecution | None = None
    request_id_token = None
    try:
        execution = _claim_task(
            db,
            task_id=task_id,
            celery_task_id=getattr(self.request, "id", None),
            worker_id=getattr(self.request, "hostname", None),
        )
        if execution is None:
            logger.info("Task %s was already claimed, terminal, or missing", task_id)
            return
        record = execution.task
        if record.request_id:
            request_id_token = request_id_context.set(record.request_id)
        # Tasks created before company scope was introduced may still contain
        # direct/scope-exit work.  They receive no tenant GUC, so RLS returns
        # zero document/vector rows rather than accidentally choosing a tenant.
        # Newly created analysis tasks always persist company_id server-side.
        if record.company_id is not None:
            set_tenant_scope(db, record.company_id)
        _sync_assistant_message(
            db,
            record,
            status="running",
            content=None,
        )
        db.commit()

        if _stop_if_cancelled(db, record):
            return

        if bool((record.result_data or {}).get("review_publish_only")):
            _publish_approved_draft(db, record, execution)
            logger.info("Task %s published approved report draft", task_id)
            return

        document_ids = [
            row.document_id
            for row in db.query(AnalysisTaskDocument)
            .filter(AnalysisTaskDocument.task_id == record.id)
            .all()
        ]
        has_frozen_attachments = (
            db.query(AnalysisTaskInputArtifactVersion)
            .filter(AnalysisTaskInputArtifactVersion.task_id == record.id)
            .first()
            is not None
        )
        attachment_context = build_task_attachment_context(
            db,
            task_id=record.id,
            company_id=record.company_id,
            storage=(
                get_artifact_processing_storage(get_settings())
                if has_frozen_attachments
                else None
            ),
        )
        planner_memory, planner_memory_manifest = select_planner_memories(
            db, company_id=record.company_id, user_id=record.user_id
        )
        context_snapshot = record.context_snapshot or {}
        append_workflow_event(
            db,
            attempt=execution.attempt,
            company_id=record.company_id,
            event_type="context_selected",
            node_name="planner",
            status="succeeded",
            details={
                "conversation": {
                    "snapshot_version": context_snapshot.get("version"),
                    "history_truncated": context_snapshot.get("history_truncated"),
                    "manifest": context_snapshot.get("context_manifest"),
                },
                "planner_memory": planner_memory_manifest,
                "attachments": attachment_context.selection_manifest,
            },
        )
        db.commit()
        workflow_kwargs: dict[str, Any] = {
            "conversation_context": record.context_snapshot,
            "planner_memory": planner_memory,
            "attachment_context": attachment_context.planner_payload,
        }
        workflow_kwargs["document_ids"] = document_ids
        workflow_kwargs["tool_runtime"] = ToolRuntime(
            db=db,
            attempt=execution.attempt,
            context=ToolRuntimeContext(
                task_id=record.id,
                company_id=record.company_id,
                allowed_document_ids=frozenset(document_ids),
            ),
        )
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
        with model_call_scope(
            db,
            task=record,
            attempt=execution.attempt,
            node_name="workflow",
        ), _maintain_execution_lease(execution):
            workflow_record = record
            workflow_result = run_analysis(
                workflow_record.question,
                workflow_record.user_id,
                company_id=workflow_record.company_id,
                stage_callback=lambda stage, node_name=None: _update_stage(
                    db, workflow_record, execution, stage, node_name
                ),
                checkpoint_callback=lambda completed_node, next_node, patch: (
                    _checkpoint_workflow_node(
                        db,
                        workflow_record,
                        execution,
                        completed_node,
                        next_node,
                        patch,
                    )
                ),
                resume_next_node=execution.resume_next_node,
                resume_state=execution.resume_state,
                **workflow_kwargs,
            )

        terminal_result = workflow_result.get("terminal_result") or {}
        if terminal_result.get("retryable"):
            raise RetryableAnalysisTaskError(
                terminal_result.get("error_code") or "retryable_workflow_failure"
            )

        if _stop_if_cancelled(db, record):
            return

        _save_workflow_result(db, record, execution, workflow_result)
        db.refresh(record)
        logger.info("Task %s completed through LangGraph", task_id)

    except RetryableAnalysisTaskError as exc:
        db.rollback()
        db.expire_all()
        if execution is None:
            return
        if self.request.retries >= self.max_retries:
            record = transition_execution(
                db,
                attempt=execution.attempt,
                task_status="failed",
                stage="completed",
                attempt_status="failed",
                error_type=type(exc).__name__,
                error_message="分析服务暂时不可用。",
                recovery_instruction="retry_budget_exhausted",
                next_node=None,
            )
            if record is None:
                return
            record.duration_ms = _duration_ms(db, record)
            _sync_assistant_message(
                db,
                record,
                status="failed",
                content=GENERIC_WORKER_FAILURE_MESSAGE,
            )
            db.commit()
            raise

        record = transition_execution(
            db,
            attempt=execution.attempt,
            task_status="retrying",
            stage="retrying",
            attempt_status="retrying",
            error_type=type(exc).__name__,
            error_message="分析服务暂时不可用。",
            recovery_instruction="retry_same_execution_scope",
            next_node=retry_resume_node(db, attempt=execution.attempt),
            retry_error_code=str(exc),
        )
        if record is None:
            return
        record.duration_ms = _duration_ms(db, record)
        _sync_assistant_message(
            db,
            record,
            status="running",
            content=RETRYING_WORKER_MESSAGE,
        )
        db.commit()
        raise self.retry(exc=exc, countdown=2 ** (self.request.retries + 1))
    except ModelBudgetExceeded as exc:
        db.rollback()
        db.expire_all()
        if execution is None:
            return
        record = transition_execution(
            db,
            attempt=execution.attempt,
            task_status="partial",
            stage="completed",
            attempt_status="partial",
            error_type=exc.code,
            error_message="模型调用预算已耗尽，未继续生成或修复内容。",
            recovery_instruction="model_budget_exhausted_stop",
            next_node=None,
        )
        if record is None:
            return
        record.duration_ms = _duration_ms(db, record)
        record.result_summary = "模型调用预算已耗尽，已保留当前可用结果与限制。"
        record.result_data = {
            "type": "model_budget_exhausted",
            "error_code": exc.code,
            "limitation": "模型调用预算已耗尽，未继续生成或修复内容。",
        }
        _sync_assistant_message(
            db,
            record,
            status="partial",
            content=record.result_summary,
        )
        db.commit()
        return
    except Exception as exc:
        if _is_retryable_exception(exc):
            db.rollback()
            db.expire_all()
            if execution is None:
                return
            retry_error = RetryableAnalysisTaskError(str(exc))
            if self.request.retries < self.max_retries:
                record = transition_execution(
                    db,
                    attempt=execution.attempt,
                    task_status="retrying",
                    stage="retrying",
                    attempt_status="retrying",
                    error_type=type(exc).__name__,
                    error_message="分析服务暂时不可用。",
                    recovery_instruction="retry_same_execution_scope",
                    next_node=retry_resume_node(db, attempt=execution.attempt),
                    retry_error_code=type(exc).__name__,
                )
                if record is None:
                    return
                record.duration_ms = _duration_ms(db, record)
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
        if execution is None:
            return
        logger.exception("Task %s failed without retry", task_id)

        record = transition_execution(
            db,
            attempt=execution.attempt,
            task_status="failed",
            stage="completed",
            attempt_status="failed",
            error_type=type(exc).__name__,
            error_message="分析任务执行失败。",
            recovery_instruction="terminal_failure",
            next_node=None,
        )
        if record is None:
            logger.info("Task %s was cancelled while handling an error", task_id)
            return

        record.duration_ms = _duration_ms(db, record)
        _sync_assistant_message(
            db,
            record,
            status="failed",
            content=GENERIC_WORKER_FAILURE_MESSAGE,
        )
        db.commit()
        raise
    finally:
        if request_id_token is not None:
            request_id_context.reset(request_id_token)
        db.close()
