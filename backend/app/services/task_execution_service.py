"""Atomic execution ownership and durable workflow checkpoints."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.analysis_task import AnalysisTask
from app.models.task_execution_attempt import TaskExecutionAttempt
from app.models.workflow_checkpoint import WorkflowCheckpoint
from app.services.workflow_event_service import append_workflow_event


LEASE_SECONDS = 120
WORKFLOW_VERSION = "v1"


@dataclass(frozen=True)
class ClaimedExecution:
    task: AnalysisTask
    attempt: TaskExecutionAttempt
    resume_next_node: str | None = None
    resume_state: dict | None = None


def _append_checkpoint(
    db: Session,
    *,
    attempt: TaskExecutionAttempt,
    sequence: int,
    completed_node: str | None,
    next_node: str | None,
    state_patch: dict,
    error_code: str | None = None,
    recovery_instruction: str | None = None,
) -> WorkflowCheckpoint:
    """Persist a checkpoint and atomically advance the attempt's liveness pointer."""
    checkpoint = WorkflowCheckpoint(
        execution_attempt_id=attempt.id,
        sequence=sequence,
        completed_node=completed_node,
        next_node=next_node,
        state_patch=state_patch,
        error_code=error_code,
        recovery_instruction=recovery_instruction,
    )
    db.add(checkpoint)
    db.flush()
    attempt.latest_checkpoint_id = checkpoint.id
    attempt.heartbeat_at = datetime.now(timezone.utc)
    return checkpoint


def _latest_resume_checkpoint(
    db: Session, *, task_id: int, excluding_attempt_id: int
) -> WorkflowCheckpoint | None:
    """Return only a completed-node snapshot, never an enter-stage marker."""
    return (
        db.query(WorkflowCheckpoint)
        .join(
            TaskExecutionAttempt,
            WorkflowCheckpoint.execution_attempt_id == TaskExecutionAttempt.id,
        )
        .filter(
            TaskExecutionAttempt.task_id == task_id,
            TaskExecutionAttempt.id != excluding_attempt_id,
            WorkflowCheckpoint.next_node.is_not(None),
            WorkflowCheckpoint.state_patch["workflow_state"].is_not(None),
        )
        .order_by(WorkflowCheckpoint.id.desc())
        .first()
    )


def claim_execution(
    db: Session, *, task_id: int, celery_task_id: str | None, worker_id: str | None
) -> ClaimedExecution | None:
    """Claim queued/retrying work; only one delivery can create an attempt."""
    now = datetime.now(timezone.utc)
    execution_id = str(uuid4())
    claimed = (
        db.query(AnalysisTask)
        .filter(
            AnalysisTask.id == task_id, AnalysisTask.status.in_(("queued", "retrying"))
        )
        .update(
            {
                AnalysisTask.status: "running",
                AnalysisTask.stage: "planning",
                AnalysisTask.started_at: now,
                AnalysisTask.celery_task_id: celery_task_id,
                AnalysisTask.active_execution_id: execution_id,
                AnalysisTask.error_message: None,
                AnalysisTask.error_type: None,
                AnalysisTask.attempt_count: AnalysisTask.attempt_count + 1,
            },
            synchronize_session=False,
        )
    )
    if not claimed:
        db.rollback()
        return None
    task = db.get(AnalysisTask, task_id)
    assert task is not None
    attempt = TaskExecutionAttempt(
        task_id=task.id,
        execution_id=execution_id,
        worker_id=worker_id,
        celery_task_id=celery_task_id,
        retry_number=task.attempt_count,
        lease_expires_at=now + timedelta(seconds=LEASE_SECONDS),
        heartbeat_at=now,
        workflow_version=WORKFLOW_VERSION,
    )
    db.add(attempt)
    db.flush()
    _append_checkpoint(
        db,
        attempt=attempt,
        sequence=0,
        completed_node=None,
        next_node="planner_node",
        state_patch={},
        recovery_instruction="resume_from_next_node",
    )
    append_workflow_event(
        db,
        attempt=attempt,
        company_id=task.company_id,
        event_type="execution_claimed",
        status="running",
        details={"retry_number": attempt.retry_number},
    )
    db.commit()
    db.refresh(task)
    db.refresh(attempt)
    checkpoint = _latest_resume_checkpoint(
        db, task_id=task.id, excluding_attempt_id=attempt.id
    )
    resume_state = (
        checkpoint.state_patch.get("workflow_state")
        if checkpoint is not None and isinstance(checkpoint.state_patch, dict)
        else None
    )
    return ClaimedExecution(
        task=task,
        attempt=attempt,
        resume_next_node=checkpoint.next_node if checkpoint is not None else None,
        resume_state=resume_state if isinstance(resume_state, dict) else None,
    )


def owns_execution(db: Session, *, task_id: int, execution_id: str) -> bool:
    return (
        db.query(AnalysisTask.id)
        .filter(
            AnalysisTask.id == task_id,
            AnalysisTask.active_execution_id == execution_id,
            AnalysisTask.status == "running",
        )
        .first()
        is not None
    )


def checkpoint_stage(
    db: Session,
    *,
    attempt: TaskExecutionAttempt,
    stage: str,
    completed_node: str | None = None,
) -> bool:
    """Persist progress only while this execution still owns the task."""
    if not owns_execution(
        db, task_id=attempt.task_id, execution_id=attempt.execution_id
    ):
        return False
    sequence = (
        db.query(func.coalesce(func.max(WorkflowCheckpoint.sequence), -1))
        .filter(WorkflowCheckpoint.execution_attempt_id == attempt.id)
        .scalar()
        + 1
    )
    _append_checkpoint(
        db,
        attempt=attempt,
        sequence=sequence,
        completed_node=completed_node,
        next_node=stage,
        state_patch={"stage": stage},
        recovery_instruction="resume_from_next_node",
    )
    db.query(AnalysisTask).filter(
        AnalysisTask.id == attempt.task_id,
        AnalysisTask.active_execution_id == attempt.execution_id,
        AnalysisTask.status == "running",
    ).update({AnalysisTask.stage: stage}, synchronize_session=False)
    attempt.lease_expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=LEASE_SECONDS
    )
    db.commit()
    return True


def checkpoint_workflow_state(
    db: Session,
    *,
    attempt: TaskExecutionAttempt,
    stage: str,
    completed_node: str,
    next_node: str | None,
    workflow_state: dict,
) -> bool:
    """Durably save safe node output while this Worker still owns the task."""
    updated = (
        db.query(AnalysisTask)
        .filter(
            AnalysisTask.id == attempt.task_id,
            AnalysisTask.active_execution_id == attempt.execution_id,
            AnalysisTask.status == "running",
        )
        .update({AnalysisTask.stage: stage}, synchronize_session=False)
    )
    if not updated:
        db.rollback()
        return False
    sequence = (
        db.query(func.coalesce(func.max(WorkflowCheckpoint.sequence), -1))
        .filter(WorkflowCheckpoint.execution_attempt_id == attempt.id)
        .scalar()
        + 1
    )
    _append_checkpoint(
        db,
        attempt=attempt,
        sequence=sequence,
        completed_node=completed_node,
        next_node=next_node,
        state_patch={"workflow_state": workflow_state},
        recovery_instruction="resume_from_next_node",
    )
    attempt.lease_expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=LEASE_SECONDS
    )
    db.commit()
    return True


def finish_execution(
    db: Session,
    *,
    attempt: TaskExecutionAttempt,
    task_status: str,
    attempt_status: str | None = None,
    result_summary: str | None,
    result_data: dict,
    error_message: str | None,
) -> bool:
    """Persist a terminal result or review hold only while ownership is current."""
    now = datetime.now(timezone.utc)
    updated = (
        db.query(AnalysisTask)
        .filter(
            AnalysisTask.id == attempt.task_id,
            AnalysisTask.active_execution_id == attempt.execution_id,
            AnalysisTask.status == "running",
        )
        .update(
            {
                AnalysisTask.status: task_status,
                AnalysisTask.stage: (
                    "awaiting_review"
                    if task_status == "awaiting_review"
                    else "completed"
                ),
                AnalysisTask.result_summary: result_summary,
                AnalysisTask.result_data: result_data,
                AnalysisTask.error_message: error_message,
                AnalysisTask.completed_at: None
                if task_status == "awaiting_review"
                else now,
                AnalysisTask.active_execution_id: None,
            },
            synchronize_session=False,
        )
    )
    if not updated:
        db.rollback()
        return False
    attempt.status = attempt_status or task_status
    attempt.finished_at = now
    _append_checkpoint(
        db,
        attempt=attempt,
        sequence=(
            db.query(func.coalesce(func.max(WorkflowCheckpoint.sequence), -1))
            .filter(WorkflowCheckpoint.execution_attempt_id == attempt.id)
            .scalar()
            + 1
        ),
        completed_node=(
            "review_submission" if task_status == "awaiting_review" else "saving_result"
        ),
        next_node=(
            "review_approval_publish" if task_status == "awaiting_review" else None
        ),
        state_patch={"task_status": task_status},
        recovery_instruction=(
            "await_human_review" if task_status == "awaiting_review" else "terminal"
        ),
    )
    append_workflow_event(
        db,
        attempt=attempt,
        company_id=(db.get(AnalysisTask, attempt.task_id).company_id),
        event_type="execution_finished",
        node_name="saving_result",
        status=task_status,
        details={"attempt_status": attempt.status},
    )
    db.commit()
    return True


def transition_execution(
    db: Session,
    *,
    attempt: TaskExecutionAttempt,
    task_status: str,
    stage: str,
    attempt_status: str,
    error_type: str | None,
    error_message: str | None,
    recovery_instruction: str,
    next_node: str | None,
) -> AnalysisTask | None:
    """Atomically relinquish an execution after a retry or failure.

    The conditional update is the ownership proof.  The caller may enrich the
    returned record (for example, its conversation message) and commit that
    work in the same transaction.  A stale Worker receives ``None`` and must
    not write anything further.
    """
    now = datetime.now(timezone.utc)
    updated = (
        db.query(AnalysisTask)
        .filter(
            AnalysisTask.id == attempt.task_id,
            AnalysisTask.active_execution_id == attempt.execution_id,
            AnalysisTask.status == "running",
        )
        .update(
            {
                AnalysisTask.status: task_status,
                AnalysisTask.stage: stage,
                AnalysisTask.error_type: error_type,
                AnalysisTask.error_message: error_message,
                AnalysisTask.completed_at: now if task_status == "failed" else None,
                AnalysisTask.active_execution_id: None,
            },
            synchronize_session=False,
        )
    )
    if not updated:
        db.rollback()
        return None

    record = db.get(AnalysisTask, attempt.task_id)
    assert record is not None
    attempt.status = attempt_status
    attempt.finished_at = now
    _append_checkpoint(
        db,
        attempt=attempt,
        sequence=(
            db.query(func.coalesce(func.max(WorkflowCheckpoint.sequence), -1))
            .filter(WorkflowCheckpoint.execution_attempt_id == attempt.id)
            .scalar()
            + 1
        ),
        completed_node=record.stage,
        next_node=next_node,
        state_patch={"task_status": task_status, "stage": stage},
        error_code=error_type,
        recovery_instruction=recovery_instruction,
    )
    append_workflow_event(
        db,
        attempt=attempt,
        company_id=record.company_id,
        event_type="execution_transitioned",
        node_name=stage,
        status=task_status,
        error_code=error_type,
        details={"recovery_instruction": recovery_instruction, "next_node": next_node},
    )
    return record


def recover_expired_executions(
    db: Session, *, now: datetime | None = None
) -> list[int]:
    """Release only still-owned expired attempts for a fresh Worker claim."""
    current = now or datetime.now(timezone.utc)
    attempts = (
        db.query(TaskExecutionAttempt)
        .filter(
            TaskExecutionAttempt.status == "running",
            TaskExecutionAttempt.lease_expires_at <= current,
        )
        .all()
    )
    task_ids: list[int] = []
    for attempt in attempts:
        updated = (
            db.query(AnalysisTask)
            .filter(
                AnalysisTask.id == attempt.task_id,
                AnalysisTask.status == "running",
                AnalysisTask.active_execution_id == attempt.execution_id,
            )
            .update(
                {
                    AnalysisTask.status: "retrying",
                    AnalysisTask.stage: "retrying",
                    AnalysisTask.active_execution_id: None,
                    AnalysisTask.error_type: "ExecutionLeaseExpired",
                    AnalysisTask.error_message: "执行租约已过期，正在恢复。",
                },
                synchronize_session=False,
            )
        )
        if updated:
            attempt.status = "expired"
            attempt.finished_at = current
            task_ids.append(attempt.task_id)
    db.commit()
    return task_ids
