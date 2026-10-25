"""Evaluate durable workflow outcomes for a single company."""

from math import ceil

from app.modules.evaluation.workflow_schemas import WorkflowEvaluation
from app.modules.workflow.audit.tool_call import ToolCallRecord
from app.modules.workflow.models import AnalysisTask
from sqlalchemy import Integer, cast, func
from sqlalchemy.orm import Session


def _percentile(values: list[int], percentile: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, ceil(len(ordered) * percentile) - 1)]


def evaluate_company_workflows(db: Session, *, company_id: int) -> WorkflowEvaluation:
    terminal = (
        db.query(AnalysisTask)
        .filter(
            AnalysisTask.company_id == company_id,
            AnalysisTask.status.in_(("completed", "partial", "failed", "cancelled")),
        )
        .all()
    )
    counts = {
        status: sum(task.status == status for task in terminal)
        for status in ("completed", "partial", "failed", "cancelled")
    }
    durations = [task.duration_ms for task in terminal if task.duration_ms is not None]
    tool_total, tool_denied = (
        db.query(
            func.count(ToolCallRecord.id),
            func.coalesce(
                func.sum(cast(ToolCallRecord.status == "denied", Integer)), 0
            ),
        )
        .join(AnalysisTask, AnalysisTask.id == ToolCallRecord.task_id)
        .filter(AnalysisTask.company_id == company_id)
        .one()
    )
    total = len(terminal)
    return WorkflowEvaluation(
        total_terminal_runs=total,
        completed_runs=counts["completed"],
        partial_runs=counts["partial"],
        failed_runs=counts["failed"],
        cancelled_runs=counts["cancelled"],
        completion_rate=counts["completed"] / total if total else 0.0,
        duration_p50_ms=_percentile(durations, 0.5),
        duration_p95_ms=_percentile(durations, 0.95),
        tool_denial_rate=(int(tool_denied) / int(tool_total) if tool_total else None),
    )
