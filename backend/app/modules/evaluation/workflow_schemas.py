"""Persisted workflow-level evaluation result, not an in-memory graph assertion."""

from pydantic import BaseModel


class WorkflowEvaluation(BaseModel):
    total_terminal_runs: int
    completed_runs: int
    partial_runs: int
    failed_runs: int
    cancelled_runs: int
    completion_rate: float
    duration_p50_ms: int | None
    duration_p95_ms: int | None
    tool_denial_rate: float | None
