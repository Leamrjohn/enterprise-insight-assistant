"""Safe, company-scoped operational metrics for analysis tasks."""

from pydantic import BaseModel


class TaskMetricsOut(BaseModel):
    total_tasks: int
    terminal_tasks: int
    completed_tasks: int
    partial_tasks: int
    failed_tasks: int
    cancelled_tasks: int
    completion_rate: float
    partial_rate: float
    retry_count: int
    duration_p50_ms: int | None
    duration_p95_ms: int | None
    model_calls: int
    model_tokens: int
    model_cost: str
    rag_sufficient_rate: float | None
    citation_failure_rate: float | None
