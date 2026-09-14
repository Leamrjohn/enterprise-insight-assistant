"""Aggregate only persisted, non-sensitive task telemetry for one company."""

from decimal import Decimal
from math import ceil

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.modules.workflow.models import AnalysisTask
from app.modules.workflow.model_call import ModelCallRecord
from app.modules.observability.schemas import TaskMetricsOut


def _percentile(values: list[int], percentile: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, ceil(len(ordered) * percentile) - 1)
    return ordered[index]


def _nested_status(result_data: object, key: str) -> str | None:
    if not isinstance(result_data, dict):
        return None
    value = result_data.get(key)
    return value.get("status") if isinstance(value, dict) else None


def _citation_validation_failed(result_data: object) -> bool | None:
    if not isinstance(result_data, dict):
        return None
    review = result_data.get("review_result")
    validation = review.get("validation") if isinstance(review, dict) else None
    if not isinstance(validation, dict) or "citations_valid" not in validation:
        return None
    return validation["citations_valid"] is False


def get_company_task_metrics(db: Session, *, company_id: int) -> TaskMetricsOut:
    tasks = (
        db.query(AnalysisTask)
        .filter(AnalysisTask.company_id == company_id)
        .order_by(AnalysisTask.id)
        .all()
    )
    status_counts = {
        status: 0 for status in ("completed", "partial", "failed", "cancelled")
    }
    for task in tasks:
        if task.status in status_counts:
            status_counts[task.status] += 1
    terminal = sum(status_counts.values())
    durations = [task.duration_ms for task in tasks if task.duration_ms is not None]
    retry_count = sum(max(0, task.attempt_count - 1) for task in tasks)

    calls, tokens, cost = (
        db.query(
            func.count(ModelCallRecord.id),
            func.coalesce(
                func.sum(
                    ModelCallRecord.prompt_tokens + ModelCallRecord.completion_tokens
                ),
                0,
            ),
            func.coalesce(func.sum(ModelCallRecord.cost), 0),
        )
        .join(AnalysisTask, AnalysisTask.id == ModelCallRecord.task_id)
        .filter(AnalysisTask.company_id == company_id)
        .one()
    )
    knowledge_statuses = [
        _nested_status(task.result_data, "knowledge_result") for task in tasks
    ]
    measured_knowledge = [status for status in knowledge_statuses if status is not None]
    sufficient = sum(status == "succeeded" for status in measured_knowledge)
    citation_results = [
        result
        for result in (_citation_validation_failed(task.result_data) for task in tasks)
        if result is not None
    ]
    return TaskMetricsOut(
        total_tasks=len(tasks),
        terminal_tasks=terminal,
        completed_tasks=status_counts["completed"],
        partial_tasks=status_counts["partial"],
        failed_tasks=status_counts["failed"],
        cancelled_tasks=status_counts["cancelled"],
        completion_rate=(status_counts["completed"] / terminal if terminal else 0.0),
        partial_rate=(status_counts["partial"] / terminal if terminal else 0.0),
        retry_count=retry_count,
        duration_p50_ms=_percentile(durations, 0.5),
        duration_p95_ms=_percentile(durations, 0.95),
        model_calls=int(calls),
        model_tokens=int(tokens),
        model_cost=str(Decimal(cost)),
        rag_sufficient_rate=(
            sufficient / len(measured_knowledge) if measured_knowledge else None
        ),
        citation_failure_rate=(
            sum(citation_results) / len(citation_results) if citation_results else None
        ),
    )
