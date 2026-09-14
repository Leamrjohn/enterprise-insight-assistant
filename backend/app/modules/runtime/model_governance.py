"""Task-scoped model budget enforcement and privacy-safe call auditing."""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterator

from sqlalchemy.orm import Session

from app.modules.workflow.models import AnalysisTask
from app.modules.workflow.model_call import ModelCallRecord
from app.modules.workflow.execution_attempt import TaskExecutionAttempt


class ModelBudgetExceeded(RuntimeError):
    """Stable, non-retryable signal: a task has exhausted its model allowance."""

    code = "model_budget_exhausted"


@dataclass(frozen=True)
class ModelCallScope:
    db: Session
    task: AnalysisTask
    attempt: TaskExecutionAttempt
    node_name: str
    prompt_version: str | None = None
    is_repair: bool = False
    reserved_prompt_tokens: int = 0


_scope: ContextVar[ModelCallScope | None] = ContextVar("model_call_scope", default=None)
_fallback_models_tried: ContextVar[tuple[str, ...] | None] = ContextVar(
    "fallback_models_tried", default=None
)


@contextmanager
def model_call_scope(
    db: Session,
    *,
    task: AnalysisTask,
    attempt: TaskExecutionAttempt,
    node_name: str,
    prompt_version: str | None = None,
    is_repair: bool = False,
) -> Iterator[None]:
    token = _scope.set(
        ModelCallScope(
            db,
            task,
            attempt,
            node_name=node_name,
            prompt_version=prompt_version,
            is_repair=is_repair,
        )
    )
    try:
        yield
    finally:
        _scope.reset(token)


@contextmanager
def model_node_scope(node_name: str, *, is_repair: bool = False) -> Iterator[None]:
    current = _scope.get()
    if current is None:
        yield
        return
    token = _scope.set(
        ModelCallScope(
            current.db,
            current.task,
            current.attempt,
            node_name=node_name,
            prompt_version=current.prompt_version,
            is_repair=is_repair,
        )
    )
    try:
        yield
    finally:
        _scope.reset(token)


@contextmanager
def fallback_chain_scope(initial_model: str) -> Iterator[None]:
    """Keep a bounded fallback chain within one logical gateway request."""
    if _fallback_models_tried.get() is not None:
        yield
        return
    token = _fallback_models_tried.set((initial_model,))
    try:
        yield
    finally:
        _fallback_models_tried.reset(token)


def next_fallback_model(current_model: str) -> str | None:
    """Return the next frozen fallback after a retryable provider failure only."""
    scope = _scope.get()
    if scope is None:
        return None
    policy = scope.task.model_policy_snapshot or {}
    maximum_attempts = max(1, int(policy.get("max_attempts", 1)))
    tried = _fallback_models_tried.get() or (current_model,)
    if len(tried) >= maximum_attempts:
        return None
    configured = policy.get("fallback_models") or []
    for candidate in configured:
        if isinstance(candidate, str) and candidate and candidate not in tried:
            _fallback_models_tried.set((*tried, candidate))
            return candidate
    return None


def reserve_model_call(
    *, provider: str, model_name: str, estimated_prompt_tokens: int = 0
) -> ModelCallScope | None:
    """Atomically consume a call slot before contacting an external provider."""
    scope = _scope.get()
    if scope is None:
        return None
    task = scope.db.get(AnalysisTask, scope.task.id, with_for_update=True)
    if task is None:
        raise ModelBudgetExceeded("task disappeared")
    budget = task.model_budget_snapshot or {}
    usage = dict(task.model_budget_usage or {})
    calls_by_node = dict(usage.get("calls_by_node") or {})
    calls = int(usage.get("calls", 0))
    node_calls = int(calls_by_node.get(scope.node_name, 0))
    tokens = int(usage.get("tokens", 0))
    repairs = int(usage.get("repairs", 0))
    current_cost = Decimal(str(usage.get("cost", "0")))
    if calls >= int(budget.get("max_calls", 0)) or node_calls >= int(
        budget.get("max_calls_per_node", 0)
    ):
        raise ModelBudgetExceeded("model call budget exhausted")
    if tokens + estimated_prompt_tokens > int(budget.get("max_total_tokens", 0)):
        raise ModelBudgetExceeded("model token budget exhausted")
    if current_cost >= Decimal(str(budget.get("max_cost", "0"))):
        raise ModelBudgetExceeded("model cost budget exhausted")
    if scope.is_repair and repairs >= int(budget.get("max_repairs", 0)):
        raise ModelBudgetExceeded("model repair budget exhausted")
    calls_by_node[scope.node_name] = node_calls + 1
    usage.update(
        {
            "calls": calls + 1,
            "tokens": tokens + estimated_prompt_tokens,
            "repairs": repairs + int(scope.is_repair),
            "calls_by_node": calls_by_node,
        }
    )
    task.model_budget_usage = usage
    scope.db.commit()
    scope.db.refresh(task)
    return ModelCallScope(
        scope.db,
        task,
        scope.attempt,
        scope.node_name,
        scope.prompt_version,
        scope.is_repair,
        estimated_prompt_tokens,
    )


def record_model_call(
    scope: ModelCallScope | None,
    *,
    provider: str,
    model_name: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    cost: float = 0.0,
    duration_ms: float = 0.0,
    result_category: str,
    error_code: str | None = None,
) -> None:
    if scope is None:
        return
    # On a transport failure the request may already have reached the provider.
    # Keep the pre-request estimate charged instead of accidentally refunding it.
    if result_category != "success" and prompt_tokens == 0:
        prompt_tokens = scope.reserved_prompt_tokens
    task = scope.db.get(AnalysisTask, scope.task.id, with_for_update=True)
    if task is None:
        return
    usage = dict(task.model_budget_usage or {})
    # reserve_model_call already counted the prompt estimate. Correct it with
    # provider-reported usage and add completion tokens only once.
    usage["tokens"] = (
        int(usage.get("tokens", 0))
        + (prompt_tokens - scope.reserved_prompt_tokens)
        + completion_tokens
    )
    usage["cost"] = str(Decimal(str(usage.get("cost", "0"))) + Decimal(str(cost)))
    task.model_budget_usage = usage
    scope.db.add(
        ModelCallRecord(
            task_id=task.id,
            execution_attempt_id=scope.attempt.id,
            node_name=scope.node_name,
            provider=provider,
            model_name=model_name,
            prompt_version=scope.prompt_version,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost=cost,
            duration_ms=round(duration_ms),
            result_category=result_category,
            error_code=error_code,
        )
    )
    scope.db.commit()
