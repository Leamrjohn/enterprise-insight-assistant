"""Safe append-only audit event helpers."""

from typing import Any

from app.modules.workflow.audit.events_models import WorkflowEvent
from app.modules.workflow.lifecycle.execution_attempt import TaskExecutionAttempt
from sqlalchemy import func
from sqlalchemy.orm import Session


def append_workflow_event(
    db: Session,
    *,
    attempt: TaskExecutionAttempt,
    company_id: int | None,
    event_type: str,
    node_name: str | None = None,
    tool_name: str | None = None,
    status: str | None = None,
    error_code: str | None = None,
    duration_ms: int | None = None,
    details: dict[str, Any] | None = None,
) -> WorkflowEvent:
    """Append metadata only; callers must never pass prompts, SQL, or document text."""
    sequence = (
        db.query(func.coalesce(func.max(WorkflowEvent.sequence), -1))
        .filter(WorkflowEvent.execution_attempt_id == attempt.id)
        .scalar()
        + 1
    )
    event = WorkflowEvent(
        task_id=attempt.task_id,
        execution_attempt_id=attempt.id,
        company_id=company_id,
        sequence=sequence,
        event_type=event_type,
        node_name=node_name,
        tool_name=tool_name,
        status=status,
        error_code=error_code,
        duration_ms=duration_ms,
        details=details or {},
    )
    db.add(event)
    return event
