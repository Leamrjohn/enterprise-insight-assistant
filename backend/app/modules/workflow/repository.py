from copy import deepcopy

from app.core.exceptions import TaskAdmissionLimitError
from app.core.settings import get_settings
from app.db.clock import database_now
from app.modules.workflow.delivery.outbox import cancel_unclaimed_analysis_task_event
from app.modules.workflow.lifecycle.capacity import require_task_capacity
from app.modules.workflow.lifecycle.execution_attempt import TaskExecutionAttempt
from app.modules.workflow.lifecycle.model_budget import configured_model_budget
from app.modules.workflow.lifecycle.task_state import require_task_transition
from app.modules.workflow.lifecycle.versioning import workflow_policy_snapshot
from app.modules.workflow.models import (
    AnalysisTask,
    AnalysisTaskDocument,
    AnalysisTaskInputArtifactVersion,
)
from sqlalchemy import text
from sqlalchemy.orm import Session

_INFLIGHT_TASK_STATUSES = ("queued", "running", "retrying")
_ADMISSION_LOCK_NAMESPACE = 9_743


def _admit_task(db: Session, *, company_id: int, settings) -> None:
    require_task_capacity(settings)
    # ponytail: global admission lock serializes local task creation; split locks only after measured contention.
    db.execute(
        text("SELECT pg_advisory_xact_lock(:namespace, :scope_id)"),
        {"namespace": _ADMISSION_LOCK_NAMESPACE, "scope_id": 0},
    )
    global_inflight = (
        db.query(AnalysisTask)
        .filter(AnalysisTask.status.in_(_INFLIGHT_TASK_STATUSES))
        .count()
    )
    if global_inflight >= settings.analysis_task_global_inflight_limit:
        raise TaskAdmissionLimitError(
            scope="global",
            limit=settings.analysis_task_global_inflight_limit,
            retry_after_seconds=settings.analysis_task_admission_retry_after_seconds,
        )

    db.execute(
        text("SELECT pg_advisory_xact_lock(:namespace, :scope_id)"),
        {"namespace": _ADMISSION_LOCK_NAMESPACE, "scope_id": company_id},
    )
    company_inflight = (
        db.query(AnalysisTask)
        .filter(
            AnalysisTask.company_id == company_id,
            AnalysisTask.status.in_(_INFLIGHT_TASK_STATUSES),
        )
        .count()
    )
    if company_inflight >= settings.analysis_task_company_inflight_limit:
        raise TaskAdmissionLimitError(
            scope="company",
            limit=settings.analysis_task_company_inflight_limit,
            retry_after_seconds=settings.analysis_task_admission_retry_after_seconds,
        )


def create_task(
    db: Session,
    user_id: int,
    question: str,
    *,
    conversation_id: int | None = None,
    input_message_id: int | None = None,
    context_snapshot: dict | None = None,
    company_id: int | None = None,
    data_source_id: int | None = None,
    schema_snapshot_id: int | None = None,
    document_ids: list[int] | None = None,
    input_artifact_version_ids: list[int] | None = None,
    parent_task_id: int | None = None,
    request_id: str | None = None,
) -> AnalysisTask:
    settings = get_settings()
    if company_id is not None:
        _admit_task(db, company_id=company_id, settings=settings)
    record = AnalysisTask(
        user_id=user_id,
        question=question,
        status="queued",
        conversation_id=conversation_id,
        input_message_id=input_message_id,
        context_snapshot=context_snapshot,
        company_id=company_id,
        data_source_id=data_source_id,
        schema_snapshot_id=schema_snapshot_id,
        parent_task_id=parent_task_id,
        request_id=request_id,
        workflow_policy_snapshot=workflow_policy_snapshot(
            settings.workflow_release_version
        ),
        model_policy_snapshot={
            "primary_model": f"{settings.llm_provider}:{settings.llm_model}",
            "fallback_models": [],
            "require_json": False,
            "allow_tool_calling": False,
            "timeout_seconds": settings.llm_timeout_seconds,
            "max_output_tokens": settings.llm_max_output_tokens,
            "max_attempts": 3,
            "model_pricing": {
                "version": settings.model_price_table_version,
                "entries": deepcopy(settings.model_price_table),
            },
        },
        model_budget_snapshot=configured_model_budget(settings),
    )
    db.add(record)
    db.flush()
    for document_id in document_ids or []:
        db.add(AnalysisTaskDocument(task_id=record.id, document_id=document_id))
    for position, artifact_version_id in enumerate(input_artifact_version_ids or []):
        db.add(
            AnalysisTaskInputArtifactVersion(
                task_id=record.id,
                artifact_version_id=artifact_version_id,
                position=position,
            )
        )
    db.refresh(record)
    return record


def get_task_document_ids(db: Session, *, task_id: int) -> list[int]:
    return [
        document_id
        for (document_id,) in (
            db.query(AnalysisTaskDocument.document_id)
            .filter(AnalysisTaskDocument.task_id == task_id)
            .order_by(AnalysisTaskDocument.document_id)
            .all()
        )
    ]


def get_task_input_artifact_version_ids(db: Session, *, task_id: int) -> list[int]:
    return [
        artifact_version_id
        for (artifact_version_id,) in (
            db.query(AnalysisTaskInputArtifactVersion.artifact_version_id)
            .filter(AnalysisTaskInputArtifactVersion.task_id == task_id)
            .order_by(AnalysisTaskInputArtifactVersion.position)
            .all()
        )
    ]


def get_task_by_id(db: Session, task_id: int, user_id: int) -> AnalysisTask | None:
    return (
        db.query(AnalysisTask)
        .filter(
            AnalysisTask.id == task_id,
            AnalysisTask.user_id == user_id,
        )
        .first()
    )


def get_tasks(db: Session, user_id: int) -> list[AnalysisTask]:
    return (
        db.query(AnalysisTask)
        .filter(
            AnalysisTask.user_id == user_id,
        )
        .order_by(AnalysisTask.id.desc())
        .all()
    )


def cancel_task(db: Session, task: AnalysisTask):
    require_task_transition(task.status, "cancelled")
    execution_id = task.active_execution_id
    task.status = "cancelled"
    task.active_execution_id = None
    if execution_id is not None:
        attempt = (
            db.query(TaskExecutionAttempt)
            .filter(
                TaskExecutionAttempt.task_id == task.id,
                TaskExecutionAttempt.execution_id == execution_id,
                TaskExecutionAttempt.status == "running",
            )
            .one_or_none()
        )
        if attempt is not None:
            attempt.status = "cancelled"
            attempt.finished_at = database_now(db)
    cancel_unclaimed_analysis_task_event(db, task_id=task.id)
    db.flush()
    return task
