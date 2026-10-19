"""Frozen workflow-release selection and safe retry rollback."""

from app.modules.workflow.audit.events import append_workflow_event
from app.modules.workflow.lifecycle.execution_attempt import TaskExecutionAttempt
from app.modules.workflow.models import AnalysisTask
from sqlalchemy.orm import Session


STABLE_WORKFLOW_VERSION = "v1"
CANDIDATE_WORKFLOW_VERSION = "v2-candidate"
SUPPORTED_WORKFLOW_VERSIONS = frozenset(
    {STABLE_WORKFLOW_VERSION, CANDIDATE_WORKFLOW_VERSION}
)


class WorkflowRollbackError(ValueError):
    """A release change is unsafe for the task's current lifecycle state."""


def workflow_policy_snapshot(version: str) -> dict:
    if version not in SUPPORTED_WORKFLOW_VERSIONS:
        raise ValueError(f"unsupported workflow version: {version}")
    return {
        "version": version,
        "rollback_version": STABLE_WORKFLOW_VERSION,
    }


def effective_workflow_version(task: AnalysisTask) -> str:
    snapshot = task.workflow_policy_snapshot or {}
    version = task.workflow_version_override or snapshot.get("version")
    if not isinstance(version, str) or version not in SUPPORTED_WORKFLOW_VERSIONS:
        raise ValueError("task has an unsupported workflow version")
    return version


def rollback_task_workflow_version(
    db: Session,
    *,
    task_id: int,
    target_version: str = STABLE_WORKFLOW_VERSION,
) -> AnalysisTask:
    """Route only a not-running retry to a verified version.

    The source snapshot stays immutable. A prior attempt remains its original
    release and keeps all cost/tool/checkpoint facts; only the next claim reads
    the explicit override.
    """
    if target_version not in SUPPORTED_WORKFLOW_VERSIONS:
        raise WorkflowRollbackError("rollback target is not a supported release")
    task = db.get(AnalysisTask, task_id, with_for_update=True)
    if task is None:
        raise WorkflowRollbackError("task not found")
    if task.status not in {"queued", "retrying"}:
        raise WorkflowRollbackError("only queued or retrying tasks can be rolled back")
    previous_version = effective_workflow_version(task)
    if previous_version == target_version:
        return task
    attempt = (
        db.query(TaskExecutionAttempt)
        .filter(TaskExecutionAttempt.task_id == task.id)
        .order_by(TaskExecutionAttempt.id.desc())
        .first()
    )
    if attempt is None:
        raise WorkflowRollbackError("rollback requires an auditable prior attempt")
    task.workflow_version_override = target_version
    append_workflow_event(
        db,
        attempt=attempt,
        company_id=task.company_id,
        event_type="workflow_version_rolled_back",
        status=task.status,
        details={"from_version": previous_version, "to_version": target_version},
    )
    db.commit()
    db.refresh(task)
    return task
