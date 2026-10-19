"""Task-scoped model budget enforcement and privacy-safe call auditing."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from uuid import uuid4

from app.core.settings import MAX_LLM_TIMEOUT_SECONDS
from app.db.clock import database_now
from app.modules.workflow.lifecycle.execution_attempt import TaskExecutionAttempt
from app.modules.workflow.audit.model_call import ModelCallRecord
from app.modules.workflow.models import AnalysisTask
from sqlalchemy.orm import Session


class ModelBudgetExceeded(RuntimeError):
    """Stable, non-retryable signal: a task has exhausted its model allowance."""

    code = "model_budget_exhausted"


CHAT_MESSAGE_OVERHEAD_TOKENS = 4


def frozen_max_output_tokens(default: int) -> int:
    """Use the task's frozen output reservation when a governed call is active."""
    scope = _scope.get()
    if scope is None:
        return default
    value = (scope.task.model_policy_snapshot or {}).get("max_output_tokens")
    return value if isinstance(value, int) and value > 0 else default


def frozen_timeout_seconds(default: int) -> int:
    """Use the task's bounded provider timeout while a governed call is active."""
    scope = _scope.get()
    if scope is None:
        return default
    value = (scope.task.model_policy_snapshot or {}).get("timeout_seconds")
    if not isinstance(value, int):
        return default
    if not 0 < value <= MAX_LLM_TIMEOUT_SECONDS:
        raise ValueError("frozen model timeout is outside the execution lease bound")
    return value


def estimate_chat_prompt_tokens(
    token_counter: Callable[[str], int],
    prompt: str,
    system_prompt: str | None,
) -> int:
    """Reserve user and system content plus conservative chat-message framing."""
    contents = [prompt] if system_prompt is None else [system_prompt, prompt]
    return sum(token_counter(content) for content in contents) + (
        len(contents) * CHAT_MESSAGE_OVERHEAD_TOKENS
    )


@dataclass(frozen=True)
class ModelCallScope:
    db: Session
    task: AnalysisTask
    attempt: TaskExecutionAttempt
    node_name: str
    prompt_version: str | None = None
    is_repair: bool = False
    reserved_prompt_tokens: int = 0
    reserved_completion_tokens: int = 0
    model_call_id: str | None = None
    reserved_cost: Decimal | None = None
    price_table_version: str | None = None
    pricing_key: str | None = None
    charge_kind: str = "provider_model"
    record: ModelCallRecord | None = None


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


def _decimal(value: object) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _price_for_call(
    policy: dict,
    *,
    provider: str,
    model_name: str,
    parameters: dict,
) -> tuple[str | None, str | None, Decimal | None, Decimal | None]:
    """Match a frozen provider/model/parameter price entry, if one exists.

    A missing or malformed entry is deliberately not interpreted as a free call.
    The most-specific compatible parameter set wins, which lets one model have
    distinct prices for e.g. cached or reasoning modes without changing code.
    """
    pricing = policy.get("model_pricing") or {}
    entries = pricing.get("entries") or []
    candidates: list[tuple[int, dict]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("provider") != provider or entry.get("model_name") != model_name:
            continue
        required = entry.get("parameters") or {}
        if not isinstance(required, dict) or any(
            parameters.get(key) != value for key, value in required.items()
        ):
            continue
        candidates.append((len(required), entry))
    if not candidates:
        return None, None, None, None
    entry = max(candidates, key=lambda candidate: candidate[0])[1]
    prompt_price = _decimal(entry.get("prompt_per_1k"))
    completion_price = _decimal(entry.get("completion_per_1k"))
    if prompt_price is None or completion_price is None:
        return None, None, None, None
    version = pricing.get("version")
    price_id = entry.get("price_id")
    if (
        not isinstance(version, str)
        or not version
        or not isinstance(price_id, str)
        or not price_id
    ):
        return None, None, None, None
    return version, price_id, prompt_price, completion_price


def _priced_cost(
    *,
    prompt_tokens: int,
    completion_tokens: int,
    prompt_price: Decimal | None,
    completion_price: Decimal | None,
) -> Decimal | None:
    if prompt_price is None or completion_price is None:
        return None
    return (
        Decimal(prompt_tokens) / Decimal(1000) * prompt_price
        + Decimal(completion_tokens) / Decimal(1000) * completion_price
    )


def reserve_model_call(
    *,
    provider: str,
    model_name: str,
    estimated_prompt_tokens: int = 0,
    reserved_completion_tokens: int = 0,
    pricing_parameters: dict | None = None,
    charge_kind: str = "provider_model",
) -> ModelCallScope | None:
    """Atomically consume a call slot before contacting an external provider."""
    scope = _scope.get()
    if scope is None:
        return None
    if provider == "local" and charge_kind == "provider_model":
        charge_kind = "simulation"
    task = scope.db.get(AnalysisTask, scope.task.id, with_for_update=True)
    if task is None:
        raise ModelBudgetExceeded("task disappeared")
    parameters = pricing_parameters or {}
    price_version, pricing_key, prompt_price, completion_price = _price_for_call(
        task.model_policy_snapshot or {},
        provider=provider,
        model_name=model_name,
        parameters=parameters,
    )
    budget = task.model_budget_snapshot or {}
    usage = dict(task.model_budget_usage or {})
    calls_by_node = dict(usage.get("calls_by_node") or {})
    calls = int(usage.get("calls", 0))
    node_calls = int(calls_by_node.get(scope.node_name, 0))
    tokens = int(usage.get("tokens", 0))
    repairs = int(usage.get("repairs", 0))
    current_cost = Decimal(str(usage.get("cost", "0")))
    current_reserved_cost = Decimal(str(usage.get("reserved_cost", "0")))
    if calls >= int(budget.get("max_calls", 0)) or node_calls >= int(
        budget.get("max_calls_per_node", 0)
    ):
        raise ModelBudgetExceeded("model call budget exhausted")
    reserved_tokens = estimated_prompt_tokens + reserved_completion_tokens
    reserved_cost = _priced_cost(
        prompt_tokens=estimated_prompt_tokens,
        completion_tokens=reserved_completion_tokens,
        prompt_price=prompt_price,
        completion_price=completion_price,
    )
    if tokens + reserved_tokens > int(budget.get("max_total_tokens", 0)):
        raise ModelBudgetExceeded("model token budget exhausted")
    maximum_cost = Decimal(str(budget.get("max_cost", "0")))
    if (
        current_cost + current_reserved_cost + (reserved_cost or Decimal(0))
        > maximum_cost
    ):
        raise ModelBudgetExceeded("model cost budget exhausted")
    if scope.is_repair and repairs >= int(budget.get("max_repairs", 0)):
        raise ModelBudgetExceeded("model repair budget exhausted")
    calls_by_node[scope.node_name] = node_calls + 1
    usage.update(
        {
            "calls": calls + 1,
            "tokens": tokens + reserved_tokens,
            "repairs": repairs + int(scope.is_repair),
            "calls_by_node": calls_by_node,
            "reserved_cost": str(current_reserved_cost + (reserved_cost or Decimal(0))),
        }
    )
    record = ModelCallRecord(
        model_call_id=str(uuid4()),
        task_id=task.id,
        execution_attempt_id=scope.attempt.id,
        node_name=scope.node_name,
        provider=provider,
        model_name=model_name,
        prompt_version=scope.prompt_version,
        model_parameters=parameters,
        price_table_version=price_version,
        pricing_key=pricing_key,
        charge_kind=charge_kind,
        billing_status="reserved",
        reserved_prompt_tokens=estimated_prompt_tokens,
        reserved_completion_tokens=reserved_completion_tokens,
        reserved_cost=reserved_cost,
        resource_usage={},
        result_category="reserved",
    )
    task.model_budget_usage = usage
    scope.db.add(record)
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
        reserved_completion_tokens,
        record.model_call_id,
        reserved_cost,
        price_version,
        pricing_key,
        charge_kind,
        record,
    )


def reserve_local_resource_call(
    *,
    resource_kind: str,
    model_name: str,
    resource_usage: dict,
) -> ModelCallScope | None:
    """Persist a local embedding/rerank operation before execution.

    These are not provider-billed model calls and therefore do not consume the
    task's paid-model budget. They still need a durable identifier, timing, and
    an explicit local-resource cost basis.
    """
    scope = _scope.get()
    if scope is None:
        return None
    task = scope.db.get(AnalysisTask, scope.task.id, with_for_update=True)
    if task is None:
        raise ModelBudgetExceeded("task disappeared")
    record = ModelCallRecord(
        model_call_id=str(uuid4()),
        task_id=task.id,
        execution_attempt_id=scope.attempt.id,
        node_name=scope.node_name,
        provider="local",
        model_name=model_name,
        prompt_version=scope.prompt_version,
        model_parameters={"resource_kind": resource_kind},
        charge_kind="local_resource",
        billing_status="reserved",
        resource_usage=resource_usage,
        result_category="reserved",
    )
    scope.db.add(record)
    scope.db.commit()
    return ModelCallScope(
        scope.db,
        task,
        scope.attempt,
        scope.node_name,
        scope.prompt_version,
        scope.is_repair,
        model_call_id=record.model_call_id,
        charge_kind="local_resource",
        record=record,
    )


def record_model_call(
    scope: ModelCallScope | None,
    *,
    provider: str,
    model_name: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    duration_ms: float = 0.0,
    result_category: str,
    error_code: str | None = None,
    prompt_template_id: str | None = None,
    prompt_hash: str | None = None,
    model_parameters: dict | None = None,
    resource_usage: dict | None = None,
) -> None:
    if scope is None or scope.record is None:
        return
    record = scope.record
    task = scope.db.get(AnalysisTask, scope.task.id, with_for_update=True)
    if task is None:
        return
    persisted_record = scope.db.get(
        ModelCallRecord,
        record.id,
        populate_existing=True,
        with_for_update=True,
    )
    if not isinstance(persisted_record, ModelCallRecord):
        # Lightweight test doubles may not distinguish ORM classes. Production
        # sessions always reload the durable row before deciding to settle.
        persisted_record = record
    if persisted_record is None or persisted_record.billing_status != "reserved":
        return
    record = persisted_record
    usage = dict(task.model_budget_usage or {})
    settled = result_category == "success" and (
        prompt_tokens > 0 or completion_tokens > 0
    )
    # The reservation stores the *amount*, not individual unit prices. Resolve
    # the frozen entry again so actual provider usage can settle it exactly.
    _version, _key, prompt_price, completion_price = _price_for_call(
        task.model_policy_snapshot or {},
        provider=provider,
        model_name=model_name,
        parameters=model_parameters or record.model_parameters,
    )
    priced_cost = _priced_cost(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        prompt_price=prompt_price,
        completion_price=completion_price,
    )
    is_local_resource = scope.charge_kind in {"local_resource", "simulation"}
    billing_status = (
        "settled"
        if (is_local_resource and result_category == "success")
        or (settled and priced_cost is not None)
        else "unknown"
    )
    current_reserved_cost = Decimal(str(usage.get("reserved_cost", "0")))
    if billing_status == "settled":
        usage["tokens"] = (
            int(usage.get("tokens", 0))
            + (prompt_tokens - scope.reserved_prompt_tokens)
            + (completion_tokens - scope.reserved_completion_tokens)
        )
        usage["reserved_cost"] = str(
            max(Decimal(0), current_reserved_cost - (scope.reserved_cost or Decimal(0)))
        )
        usage["cost"] = str(
            Decimal(str(usage.get("cost", "0"))) + (priced_cost or Decimal(0))
        )
    else:
        # A timeout or missing provider usage can still have been billed. Keep
        # the reservation charged and expose the uncertainty instead of making
        # it look like a zero-cost failure.
        usage["unknown_cost_calls"] = int(usage.get("unknown_cost_calls", 0)) + 1
    task.model_budget_usage = usage
    record.provider = provider
    record.model_name = model_name
    record.prompt_template_id = prompt_template_id
    record.prompt_hash = prompt_hash
    record.model_parameters = model_parameters or record.model_parameters
    record.prompt_tokens = prompt_tokens
    record.completion_tokens = completion_tokens
    record.cost = (
        Decimal(0)
        if billing_status == "settled" and is_local_resource
        else priced_cost if billing_status == "settled" else None
    )
    record.duration_ms = round(duration_ms)
    if resource_usage is not None:
        record.resource_usage = resource_usage
    record.result_category = result_category
    record.error_code = error_code
    record.billing_status = billing_status
    record.settled_at = database_now(scope.db)
    scope.db.commit()


def prompt_provenance(
    prompt: str,
    system_prompt: str | None,
    *,
    json_mode: bool,
    timeout_seconds: float | None = None,
    temperature: float | None = None,
    max_output_tokens: int | None = None,
) -> dict:
    """Return privacy-safe identifiers for the exact model request content."""
    system_text = system_prompt or ""
    template_hash = sha256(system_text.encode("utf-8")).hexdigest()
    request_hash = sha256(f"{system_text}\0{prompt}".encode()).hexdigest()
    parameters = {"json_mode": json_mode}
    for name, value in {
        "timeout_seconds": timeout_seconds,
        "temperature": temperature,
        "max_output_tokens": max_output_tokens,
    }.items():
        if value is not None:
            parameters[name] = value
    return {
        "prompt_template_id": f"system-sha256:{template_hash}",
        "prompt_hash": request_hash,
        "model_parameters": parameters,
    }
