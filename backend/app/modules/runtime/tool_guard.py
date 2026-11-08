"""What protects a tool from its own outages: retries, a circuit breaker, a switch.

A breaker counts only infrastructure failures.  A model's bad SQL says nothing
about the database, so it must never open the circuit.  None of this decides
permissions: every guarded tool still sits behind ToolRuntime.
"""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from typing import Literal, Protocol, cast

from app.modules.analysis.tool_protocol import Tool, ToolInput, ToolOutput
from app.modules.runtime.tool_loop import Outcome

logger = logging.getLogger(__name__)

# Denials stop the loop at once: asking again cannot change who the user is.
DENIED_CODES = frozenset(
    {
        "tool_not_allowlisted",
        "tool_schema_unregistered",
        "tool_company_scope_missing",
        "tool_company_scope_denied",
        "tool_current_authorization_denied",
        "tool_document_scope_denied",
        "tool_document_current_authorization_denied",
        "tool_task_missing",
    }
)
EXHAUSTED_CODES = frozenset({"tool_budget_exhausted"})
CIRCUIT_OPEN_CODE = "tool_circuit_open"
INFRASTRUCTURE_CODES = frozenset(
    {
        "business_db_execution_failed",
        "sql_statement_timeout",
        "mcp_transport_unavailable",
        "mcp_evidence_read_failed",
        "mcp_evidence_read_malformed",
        "mcp_sdk_version_mismatch",
    }
)


def is_infrastructure_failure(output: ToolOutput) -> bool:
    """True when the tool, not the request, is what failed."""
    if output.success or output.model_feedback:
        return False
    if output.error_code is None:  # RAGTool reports retrieval outages without a code.
        return True
    # A timeout is usually the statement's fault, so it is left for the model to fix.
    return (
        output.error_code in INFRASTRUCTURE_CODES
        and output.error_code != "sql_statement_timeout"
    )


def outcome_of_failure(output: ToolOutput) -> Outcome:
    """How a tool's failure counts in the tool loop."""
    if output.error_code in DENIED_CODES:
        return "denied"
    if output.error_code in EXHAUSTED_CODES:
        return "exhausted"
    # An outage first: some transports flag themselves repairable for the fixed
    # route's retry, but no rewording by the model can bring a service back.
    if is_infrastructure_failure(output):
        return "unavailable"
    if output.repairable or output.model_feedback:
        return "repairable"
    return "unavailable"


class BreakerStore(Protocol):
    def incr(self, key: str) -> int: ...
    def expire(self, key: str, seconds: int) -> object: ...
    def set(
        self, key: str, value: str, *, nx: bool = False, ex: int | None = None
    ) -> object: ...
    def exists(self, key: str) -> int: ...
    def delete(self, *keys: str) -> object: ...


class CircuitBreaker:
    """Open after repeated failures, then let one call test whether it recovered.

    State lives in a shared store because workers are separate processes.  If the
    store itself fails the breaker allows the call: it protects the tool, it is
    not a security control.
    """

    def __init__(
        self,
        key: str,
        store: BreakerStore,
        *,
        threshold: int = 5,
        window_seconds: int = 60,
        cooldown_seconds: int = 30,
        probe_seconds: int = 30,
    ) -> None:
        self._key = f"tool-circuit:{key}"
        self._store = store
        self._threshold = threshold
        self._window = window_seconds
        self._cooldown = cooldown_seconds
        self._probe_seconds = probe_seconds

    def _safely(self, action: Callable[[], object], fallback: object) -> object:
        try:
            return action()
        except Exception:
            logger.warning("Circuit breaker store unavailable", exc_info=True)
            return fallback

    def before_call(self) -> Literal["closed", "probe", "open"]:
        def decide() -> str:
            if self._store.exists(f"{self._key}:open"):
                return "open"
            if not self._store.exists(f"{self._key}:tripped"):
                return "closed"
            acquired = self._store.set(
                f"{self._key}:probe", "1", nx=True, ex=self._probe_seconds
            )
            return "probe" if acquired else "open"

        return self._safely(decide, "closed")  # type: ignore[return-value]

    def record_success(self) -> None:
        self._safely(
            lambda: self._store.delete(
                f"{self._key}:failures",
                f"{self._key}:tripped",
                f"{self._key}:probe",
            ),
            None,
        )

    def record_failure(self) -> None:
        def record() -> None:
            failures_key = f"{self._key}:failures"
            failures = self._store.incr(failures_key)
            if failures == 1:
                self._store.expire(failures_key, self._window)
            tripped = self._store.exists(f"{self._key}:tripped")
            if failures >= self._threshold or tripped:
                self._store.set(f"{self._key}:open", "1", ex=self._cooldown)
                self._store.set(f"{self._key}:tripped", "1")
                self._store.delete(f"{self._key}:probe")
                logger.warning("Tool circuit opened", extra={"circuit": self._key})

        self._safely(record, None)


class GuardedTool(Tool):
    """Retry outages with backoff, and stop calling a tool that keeps failing."""

    def __init__(
        self,
        tool: Tool,
        breaker: CircuitBreaker,
        *,
        retries: int = 1,
        backoff_seconds: float = 0.5,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._tool = tool
        self._breaker = breaker
        self._retries = retries
        self._backoff = backoff_seconds
        self._sleep = sleep

    @property
    def name(self) -> str:
        return self._tool.name

    @property
    def description(self) -> str:
        return self._tool.description

    def execute(self, input: ToolInput) -> ToolOutput:
        if self._breaker.before_call() == "open":
            return ToolOutput(
                success=False,
                error="该工具连续失败，已暂停调用，稍后会自动试探恢复。",
                error_code=CIRCUIT_OPEN_CODE,
            )
        output = self._tool.execute(input)
        for attempt in range(self._retries):
            if not is_infrastructure_failure(output):
                break
            self._sleep(self._backoff * (2**attempt) * random.uniform(0.8, 1.2))
            output = self._tool.execute(input)
        if is_infrastructure_failure(output):
            self._breaker.record_failure()
        else:
            self._breaker.record_success()
        return output


class FallbackTool(Tool):
    """Switch to a tool of the same kind when the first one is out of service."""

    def __init__(self, primary: Tool, secondary: Tool) -> None:
        self._primary = primary
        self._secondary = secondary

    @property
    def name(self) -> str:
        return self._primary.name

    @property
    def description(self) -> str:
        return self._primary.description

    def execute(self, input: ToolInput) -> ToolOutput:
        output = self._primary.execute(input)
        if output.error_code != CIRCUIT_OPEN_CODE and not is_infrastructure_failure(
            output
        ):
            return output
        logger.warning(
            "Tool switched", extra={"tool": self.name, "from": output.error_code}
        )
        switched = self._secondary.execute(input)
        if switched.success and isinstance(switched.data, dict):
            switched.data = {**switched.data, "switched_from": output.error_code}
        return switched


def redis_breaker_store() -> BreakerStore:
    import redis
    from app.core.settings import get_settings

    # redis-py's stubs type replies loosely; the client satisfies BreakerStore.
    return cast(
        BreakerStore,
        redis.Redis.from_url(
            get_settings().redis_url,
            socket_timeout=0.2,
            socket_connect_timeout=0.2,
        ),
    )
