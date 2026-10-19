"""Atomic execution ownership and durable workflow checkpoints."""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

from app.core.settings import EXECUTION_LEASE_SECONDS
from app.db.clock import database_now
from app.modules.workflow.checkpoint import (
    CHECKPOINT_SCHEMA_VERSION,
    WorkflowCheckpoint,
)
from app.modules.workflow.events import append_workflow_event
from app.modules.workflow.execution_attempt import TaskExecutionAttempt
from app.modules.workflow.model_call import ModelCallRecord
from app.modules.workflow.models import (
    AnalysisTask,
    AnalysisTaskDocument,
    AnalysisTaskInputArtifactVersion,
)
from app.modules.workflow.recovery import (
    apply_recovery_decision,
    recovery_decision_for_node,
)
from app.modules.workflow.task_state import require_task_transition
from app.modules.workflow.versioning import effective_workflow_version
from sqlalchemy import func
from sqlalchemy.orm import Session

LEASE_SECONDS = EXECUTION_LEASE_SECONDS


def execution_heartbeat_interval_seconds() -> int:
    """Renew well before expiry without adding another runtime setting."""
    return max(1, LEASE_SECONDS // 3)


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
    timestamp: datetime | None = None,
) -> WorkflowCheckpoint:
    """Persist a checkpoint and atomically advance the attempt's liveness pointer."""
    checkpoint = WorkflowCheckpoint(
        execution_attempt_id=attempt.id,
        sequence=sequence,
        completed_node=completed_node,
        next_node=next_node,
        state_patch=state_patch,
        schema_version=CHECKPOINT_SCHEMA_VERSION,
        task_input_fingerprint=_task_input_fingerprint(db, task_id=attempt.task_id),
        error_code=error_code,
        recovery_instruction=recovery_instruction,
    )
    db.add(checkpoint)
    db.flush()
    attempt.latest_checkpoint_id = checkpoint.id
    attempt.heartbeat_at = timestamp or database_now(db)
    return checkpoint


def _task_input_fingerprint(db: Session, *, task_id: int) -> str:
    """Hash the frozen task contract required to safely reuse a checkpoint."""
    task = db.get(AnalysisTask, task_id)
    if task is None:
        raise RuntimeError("checkpoint task does not exist")
    document_ids = [
        document_id
        for (document_id,) in db.query(AnalysisTaskDocument.document_id)
        .filter(AnalysisTaskDocument.task_id == task.id)
        .order_by(AnalysisTaskDocument.document_id)
        .all()
    ]
    artifact_version_ids = [
        artifact_version_id
        for (artifact_version_id,) in db.query(
            AnalysisTaskInputArtifactVersion.artifact_version_id
        )
        .filter(AnalysisTaskInputArtifactVersion.task_id == task.id)
        .order_by(AnalysisTaskInputArtifactVersion.position)
        .all()
    ]
    contract = {
        "question": task.question,
        "company_id": task.company_id,
        "data_source_id": task.data_source_id,
        "schema_snapshot_id": task.schema_snapshot_id,
        "context_snapshot": task.context_snapshot,
        "workflow_policy_snapshot": task.workflow_policy_snapshot,
        "model_policy_snapshot": task.model_policy_snapshot,
        "document_ids": document_ids,
        "input_artifact_version_ids": artifact_version_ids,
    }
    encoded = json.dumps(contract, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _latest_resume_checkpoint(
    db: Session, *, task_id: int, excluding_attempt_id: int
) -> WorkflowCheckpoint | None:
    """Return only a completed-node snapshot, never an enter-stage marker."""
    expected_fingerprint = _task_input_fingerprint(db, task_id=task_id)
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
            WorkflowCheckpoint.schema_version == CHECKPOINT_SCHEMA_VERSION,
            WorkflowCheckpoint.task_input_fingerprint == expected_fingerprint,
        )
        .order_by(WorkflowCheckpoint.id.desc())
        .first()
    )


def _resume_checkpoint_rejection_reason(
    db: Session, *, task_id: int, excluding_attempt_id: int
) -> str | None:
    """Explain why the newest resumable-looking snapshot is unsafe to reuse."""
    checkpoint = (
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
    if checkpoint is None:
        return None
    if checkpoint.schema_version != CHECKPOINT_SCHEMA_VERSION:
        return "checkpoint_schema_version_incompatible"
    if checkpoint.task_input_fingerprint != _task_input_fingerprint(db, task_id=task_id):
        return "checkpoint_input_contract_changed"
    return None


def _latest_stateful_checkpoint_for_attempt(
    db: Session, *, attempt_id: int
) -> WorkflowCheckpoint | None:
    """Return the last durable graph snapshot from one specific prior attempt."""
    return (
        db.query(WorkflowCheckpoint)
        .filter(
            WorkflowCheckpoint.execution_attempt_id == attempt_id,
            WorkflowCheckpoint.next_node.is_not(None),
            WorkflowCheckpoint.state_patch["workflow_state"].is_not(None),
        )
        .order_by(WorkflowCheckpoint.id.desc())
        .first()
    )


def _latest_stateful_checkpoint_before(
    db: Session, *, attempt_id: int, before_checkpoint_id: int
) -> WorkflowCheckpoint | None:
    """Return the prior trusted snapshot, excluding a failed node's own output."""
    return (
        db.query(WorkflowCheckpoint)
        .filter(
            WorkflowCheckpoint.execution_attempt_id == attempt_id,
            WorkflowCheckpoint.id < before_checkpoint_id,
            WorkflowCheckpoint.next_node.is_not(None),
            WorkflowCheckpoint.state_patch["workflow_state"].is_not(None),
        )
        .order_by(WorkflowCheckpoint.id.desc())
        .first()
    )


def retry_resume_node(db: Session, *, attempt: TaskExecutionAttempt) -> str | None:
    """Read the node whose execution was last entered by this attempt."""
    checkpoint = (
        db.query(WorkflowCheckpoint)
        .filter(
            WorkflowCheckpoint.execution_attempt_id == attempt.id,
            WorkflowCheckpoint.completed_node.is_not(None),
        )
        .order_by(WorkflowCheckpoint.id.desc())
        .first()
    )
    return checkpoint.completed_node if checkpoint is not None else None


def _retry_resume_state(
    db: Session,
    *,
    failed_attempt_id: int,
    failed_node: str,
    error_code: str,
    retry_number: int,
) -> dict | None:
    """Recover before one failed node, retaining only earlier trusted state."""
    latest = _latest_stateful_checkpoint_for_attempt(db, attempt_id=failed_attempt_id)
    source = latest
    if latest is not None and latest.completed_node == failed_node:
        source = _latest_stateful_checkpoint_before(
            db,
            attempt_id=failed_attempt_id,
            before_checkpoint_id=latest.id,
        )
    state = source.state_patch.get("workflow_state") if source is not None else None
    resume_state = dict(state) if isinstance(state, dict) else {}
    persisted_decision = resume_state.get("recovery_decision")
    decision = recovery_decision_for_node(failed_node)
    if isinstance(persisted_decision, dict):
        candidate = recovery_decision_for_node(
            str(persisted_decision.get("resume_node"))
        )
        if candidate is not None and candidate.resume_node == failed_node:
            decision = candidate
    if decision is not None:
        resume_state = apply_recovery_decision(resume_state, decision)
    resume_state["retry_context"] = {
        "failed_node": failed_node,
        "error_code": error_code,
        "retry_number": retry_number,
        "recovery_mode": decision.mode if decision is not None else "retry_node",
    }
    return resume_state


def claim_execution(
    db: Session, *, task_id: int, celery_task_id: str | None, worker_id: str | None
) -> ClaimedExecution | None:
    """Claim queued/retrying work; only one delivery can create an attempt."""
    now = database_now(db)
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
                # Task duration is the wall-clock work interval beginning at
                # the first successful claim.  Per-attempt timing is held by
                # TaskExecutionAttempt, so a retry must not reset this value.
                AnalysisTask.started_at: func.coalesce(AnalysisTask.started_at, now),
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
        task = db.get(AnalysisTask, task_id)
        if task is not None and task.active_execution_id is not None:
            attempt = (
                db.query(TaskExecutionAttempt)
                .filter(
                    TaskExecutionAttempt.task_id == task.id,
                    TaskExecutionAttempt.execution_id == task.active_execution_id,
                )
                .one_or_none()
            )
            if attempt is not None:
                append_workflow_event(
                    db,
                    attempt=attempt,
                    company_id=task.company_id,
                    event_type="execution_claim_rejected",
                    node_name="claim_execution",
                    status="rejected",
                    error_code="execution_already_claimed",
                    details={"operation": "claim_execution"},
                )
                db.commit()
        return None
    task = db.get(AnalysisTask, task_id)
    assert task is not None
    # The claim uses a bulk UPDATE with synchronize_session=False.  Refresh before
    # using attempt_count so the attempt records this delivery's real retry number.
    db.refresh(task)
    attempt = TaskExecutionAttempt(
        task_id=task.id,
        execution_id=execution_id,
        worker_id=worker_id,
        celery_task_id=celery_task_id,
        retry_number=task.attempt_count,
        lease_expires_at=now + timedelta(seconds=LEASE_SECONDS),
        heartbeat_at=now,
        workflow_version=effective_workflow_version(task),
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
        timestamp=now,
    )
    append_workflow_event(
        db,
        attempt=attempt,
        company_id=task.company_id,
        event_type="execution_claimed",
        status="running",
        details={"retry_number": attempt.retry_number},
    )
    # Broker acceptance is not delivery.  Only this successful atomic task claim
    # records that the outbox event reached one effective Worker execution.
    from app.modules.workflow.outbox import mark_analysis_task_event_worker_claimed

    mark_analysis_task_event_worker_claimed(
        db, task_id=task.id, execution_id=execution_id
    )
    db.commit()
    db.refresh(task)
    db.refresh(attempt)
    previous_checkpoint = (
        db.query(WorkflowCheckpoint)
        .join(
            TaskExecutionAttempt,
            WorkflowCheckpoint.execution_attempt_id == TaskExecutionAttempt.id,
        )
        .filter(
            TaskExecutionAttempt.task_id == task.id,
            TaskExecutionAttempt.id != attempt.id,
        )
        .order_by(WorkflowCheckpoint.id.desc())
        .first()
    )
    if (
        previous_checkpoint is not None
        and previous_checkpoint.recovery_instruction == "retry_same_execution_scope"
    ):
        failed_node = previous_checkpoint.next_node
        patch = previous_checkpoint.state_patch
        error_code = (
            patch.get("retry_error_code")
            if isinstance(patch, dict)
            else None
        ) or previous_checkpoint.error_code or "retryable_execution_error"
        if isinstance(failed_node, str):
            resume_state = _retry_resume_state(
                db,
                failed_attempt_id=previous_checkpoint.execution_attempt_id,
                failed_node=failed_node,
                error_code=error_code,
                retry_number=attempt.retry_number,
            )
            # Frozen scope and budget are reloaded from AnalysisTask.  The graph
            # restarts only the failed node, with outputs from earlier nodes intact.
            return ClaimedExecution(
                task=task,
                attempt=attempt,
                resume_next_node=failed_node,
                resume_state=resume_state,
            )
        # No entered node was durably recorded.  Starting from immutable inputs is
        # safer than guessing a node or reusing terminal state.
        return ClaimedExecution(task=task, attempt=attempt)
    checkpoint = _latest_resume_checkpoint(
        db, task_id=task.id, excluding_attempt_id=attempt.id
    )
    if checkpoint is None:
        rejection_reason = _resume_checkpoint_rejection_reason(
            db, task_id=task.id, excluding_attempt_id=attempt.id
        )
        if rejection_reason is not None:
            append_workflow_event(
                db,
                attempt=attempt,
                company_id=task.company_id,
                event_type="checkpoint_resume_rejected",
                status="running",
                details={"reason": rejection_reason},
            )
            db.commit()
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


def renew_execution_lease(
    db: Session, *, task_id: int, execution_id: str
) -> bool:
    """Extend a still-live execution lease from a dedicated Worker Session."""
    attempt = (
        db.query(TaskExecutionAttempt)
        .filter(
            TaskExecutionAttempt.task_id == task_id,
            TaskExecutionAttempt.execution_id == execution_id,
            TaskExecutionAttempt.status == "running",
        )
        .with_for_update()
        .one_or_none()
    )
    if attempt is None:
        db.rollback()
        return False

    now = database_now(db)
    if attempt.lease_expires_at <= now:
        db.rollback()
        return False

    task = (
        db.query(AnalysisTask)
        .filter(
            AnalysisTask.id == task_id,
            AnalysisTask.active_execution_id == execution_id,
            AnalysisTask.status == "running",
        )
        .with_for_update()
        .one_or_none()
    )
    if task is None:
        db.rollback()
        return False

    attempt.heartbeat_at = now
    attempt.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
    db.commit()
    return True


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
    now = database_now(db)
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
        timestamp=now,
    )
    db.query(AnalysisTask).filter(
        AnalysisTask.id == attempt.task_id,
        AnalysisTask.active_execution_id == attempt.execution_id,
        AnalysisTask.status == "running",
    ).update({AnalysisTask.stage: stage}, synchronize_session=False)
    attempt.lease_expires_at = now + timedelta(
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
    now = database_now(db)
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
        timestamp=now,
    )
    attempt.lease_expires_at = now + timedelta(
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
    require_task_transition("running", task_status)
    now = database_now(db)
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
        task = db.get(AnalysisTask, attempt.task_id)
        if task is not None:
            append_workflow_event(
                db,
                attempt=attempt,
                company_id=task.company_id,
                event_type="execution_write_rejected",
                node_name="saving_result",
                status="rejected",
                error_code="execution_fence_lost",
                details={"operation": "finish_execution"},
            )
            db.commit()
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
        timestamp=now,
    )
    task = db.get(AnalysisTask, attempt.task_id)
    if task is None:
        raise RuntimeError("analysis task disappeared before execution completion")
    append_workflow_event(
        db,
        attempt=attempt,
        company_id=task.company_id,
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
    retry_error_code: str | None = None,
) -> AnalysisTask | None:
    """Atomically relinquish an execution after a retry or failure.

    The conditional update is the ownership proof.  The caller may enrich the
    returned record (for example, its conversation message) and commit that
    work in the same transaction.  A stale Worker receives ``None`` and must
    not write anything further.
    """
    require_task_transition("running", task_status)
    now = database_now(db)
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
        state_patch={
            "task_status": task_status,
            "stage": stage,
            **(
                {"retry_error_code": retry_error_code}
                if retry_error_code is not None
                else {}
            ),
        },
        error_code=error_type,
        recovery_instruction=recovery_instruction,
        timestamp=now,
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
    current = now or database_now(db)
    attempt_ids = [
        attempt_id
        for (attempt_id,) in db.query(TaskExecutionAttempt.id)
        .filter(
            TaskExecutionAttempt.status == "running",
            TaskExecutionAttempt.lease_expires_at <= current,
        )
        .all()
    ]
    task_ids: list[int] = []
    for attempt_id in attempt_ids:
        attempt = (
            db.query(TaskExecutionAttempt)
            .filter(
                TaskExecutionAttempt.id == attempt_id,
                TaskExecutionAttempt.status == "running",
            )
            .with_for_update()
            .one_or_none()
        )
        if attempt is None or attempt.lease_expires_at > current:
            continue
        task = (
            db.query(AnalysisTask)
            .filter(
                AnalysisTask.id == attempt.task_id,
                AnalysisTask.status == "running",
                AnalysisTask.active_execution_id == attempt.execution_id,
            )
            .with_for_update()
            .one_or_none()
        )
        if task is not None:
            task.status = "retrying"
            task.stage = "retrying"
            task.active_execution_id = None
            task.error_type = "ExecutionLeaseExpired"
            task.error_message = "执行租约已过期，正在恢复。"
            unsettled_calls = (
                db.query(ModelCallRecord)
                .filter(
                    ModelCallRecord.execution_attempt_id == attempt.id,
                    ModelCallRecord.billing_status == "reserved",
                )
                .with_for_update()
                .all()
            )
            if unsettled_calls:
                usage = dict(task.model_budget_usage or {})
                usage["unknown_cost_calls"] = int(
                    usage.get("unknown_cost_calls", 0)
                ) + len(unsettled_calls)
                task.model_budget_usage = usage
                for call in unsettled_calls:
                    call.billing_status = "unknown"
                    call.result_category = "unknown"
                    call.error_code = "execution_lease_expired_before_settlement"
                    call.settled_at = current
            attempt.status = "expired"
            attempt.finished_at = current
            task_ids.append(attempt.task_id)
    db.commit()
    return task_ids
