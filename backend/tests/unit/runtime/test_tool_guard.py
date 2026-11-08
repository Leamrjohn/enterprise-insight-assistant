"""Fault drills for retries, the circuit breaker and the same-kind switch."""

from app.modules.analysis.tool_protocol import Tool, ToolInput, ToolOutput
from app.modules.runtime.tool_guard import (
    CIRCUIT_OPEN_CODE,
    CircuitBreaker,
    FallbackTool,
    GuardedTool,
    is_infrastructure_failure,
    outcome_of_failure,
)

DOWN = ToolOutput(
    success=False, error="down", error_code="business_db_execution_failed"
)
UP = ToolOutput(success=True, data={"rows": []})
BAD_SQL = ToolOutput(
    success=False,
    error="x",
    error_code="business_db_execution_failed",
    model_feedback="column does not exist",
)


class _Store:
    """In-memory store whose keys expire on a controllable clock."""

    def __init__(self):
        self.now = 0
        self.values = {}
        self.expiry = {}

    def _alive(self, key):
        if key in self.expiry and self.expiry[key] <= self.now:
            self.values.pop(key, None)
            self.expiry.pop(key)
        return key in self.values

    def incr(self, key):
        self.values[key] = (self.values[key] if self._alive(key) else 0) + 1
        return self.values[key]

    def expire(self, key, seconds):
        self.expiry[key] = self.now + seconds

    def set(self, key, value, *, nx=False, ex=None):
        if nx and self._alive(key):
            return None
        self.values[key] = value
        self.expiry.pop(key, None)
        if ex is not None:
            self.expiry[key] = self.now + ex
        return True

    def exists(self, key):
        return int(self._alive(key))

    def delete(self, *keys):
        for key in keys:
            self.values.pop(key, None)
            self.expiry.pop(key, None)


class _Tool(Tool):
    def __init__(self, *outputs):
        self.outputs = list(outputs)
        self.calls = 0

    @property
    def name(self):
        return "sql_query"

    @property
    def description(self):
        return "d"

    def execute(self, input):
        self.calls += 1
        return self.outputs.pop(0) if len(self.outputs) > 1 else self.outputs[0]


def _breaker(store, **kwargs):
    return CircuitBreaker(
        "sql:1", store, **{"threshold": 3, "cooldown_seconds": 30, **kwargs}
    )


def _guard(tool, store, **kwargs):
    return GuardedTool(
        tool, _breaker(store), retries=0, sleep=lambda _s: None, **kwargs
    )


def _call(tool):
    return tool.execute(ToolInput(parameters={}))


def test_an_outage_is_retried_by_code_and_can_recover():
    tool = _Tool(DOWN, UP)
    guarded = GuardedTool(tool, _breaker(_Store()), sleep=lambda _s: None)
    assert _call(guarded).success
    assert tool.calls == 2


def test_a_bad_statement_is_not_retried_and_does_not_count_against_the_database():
    tool = _Tool(BAD_SQL)
    store = _Store()
    guarded = GuardedTool(tool, _breaker(store), sleep=lambda _s: None)
    for _ in range(10):
        assert _call(guarded).error_code != CIRCUIT_OPEN_CODE
    assert tool.calls == 10


def test_the_circuit_opens_after_repeated_outages_and_stops_calling_the_tool():
    tool = _Tool(DOWN)
    guarded = _guard(tool, _Store())
    for _ in range(3):
        _call(guarded)
    assert tool.calls == 3
    assert _call(guarded).error_code == CIRCUIT_OPEN_CODE
    assert tool.calls == 3


def test_after_the_cooldown_one_probe_is_allowed_and_success_closes_it():
    tool = _Tool(DOWN, DOWN, DOWN, UP)
    store = _Store()
    guarded = _guard(tool, store)
    for _ in range(3):
        _call(guarded)
    store.now = 31
    assert _call(guarded).success
    assert _call(guarded).success
    assert tool.calls == 5


def test_only_one_caller_gets_the_probe():
    breaker = _breaker(_Store(), threshold=1)
    breaker.record_failure()
    breaker._store.now = 31
    assert breaker.before_call() == "probe"
    assert breaker.before_call() == "open"


def test_a_failed_probe_opens_the_circuit_again():
    tool = _Tool(DOWN)
    store = _Store()
    guarded = _guard(tool, store)
    for _ in range(3):
        _call(guarded)
    store.now = 31
    assert _call(guarded).error_code == "business_db_execution_failed"
    assert tool.calls == 4
    assert _call(guarded).error_code == CIRCUIT_OPEN_CODE
    assert tool.calls == 4


def test_a_store_outage_lets_the_call_through():
    class Broken:
        def __getattr__(self, _name):
            def fail(*_a, **_k):
                raise ConnectionError

            return fail

    tool = _Tool(UP)
    assert _call(_guard(tool, Broken())).success


def test_a_primary_outage_switches_to_the_same_kind_of_tool_and_says_so():
    secondary = _Tool(UP)
    output = _call(FallbackTool(_Tool(DOWN), secondary))
    assert output.success
    assert output.data["switched_from"] == "business_db_execution_failed"


def test_an_open_circuit_switches_too():
    open_circuit = ToolOutput(success=False, error="x", error_code=CIRCUIT_OPEN_CODE)
    assert _call(FallbackTool(_Tool(open_circuit), _Tool(UP))).success


def test_a_denial_never_switches_tools():
    denied = ToolOutput(
        success=False, error="x", error_code="tool_document_scope_denied"
    )
    secondary = _Tool(UP)
    output = _call(FallbackTool(_Tool(denied), secondary))
    assert not output.success
    assert secondary.calls == 0


def test_how_each_failure_counts_in_the_loop():
    assert outcome_of_failure(
        ToolOutput(False, error_code="tool_company_scope_denied")
    ) == ("denied")
    assert (
        outcome_of_failure(ToolOutput(False, error_code="tool_budget_exhausted"))
        == "exhausted"
    )
    assert outcome_of_failure(BAD_SQL) == "repairable"
    assert (
        outcome_of_failure(
            ToolOutput(False, error_code="sql_statement_timeout", repairable=True)
        )
        == "repairable"
    )
    assert outcome_of_failure(DOWN) == "unavailable"
    assert (
        outcome_of_failure(ToolOutput(False, error_code=CIRCUIT_OPEN_CODE))
        == "unavailable"
    )


def test_a_timeout_is_not_counted_as_an_outage():
    assert not is_infrastructure_failure(
        ToolOutput(False, error_code="sql_statement_timeout", repairable=True)
    )
