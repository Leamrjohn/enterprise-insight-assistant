import pytest

from app.core.gateway.local import LocalModelGateway
from app.services.model_governance import (
    ModelBudgetExceeded,
    model_call_scope,
    model_node_scope,
    record_model_call,
    reserve_model_call,
)


class FakeDb:
    def __init__(self, task) -> None:
        self.task = task
        self.records = []
        self.commits = 0

    def get(self, model, identity, **kwargs):
        return self.task

    def add(self, record) -> None:
        self.records.append(record)

    def commit(self) -> None:
        self.commits += 1

    def refresh(self, value) -> None:
        return None


class Task:
    id = 7
    model_policy_snapshot = {}
    model_budget_snapshot = {
        "max_calls": 1,
        "max_calls_per_node": 1,
        "max_total_tokens": 1000,
        "max_cost": "1.00",
        "max_repairs": 2,
    }
    model_budget_usage = {"calls": 0, "tokens": 0, "cost": "0.00", "calls_by_node": {}}


class Attempt:
    id = 9


def test_budget_is_reserved_before_gateway_request_and_audited_without_text() -> None:
    task = Task()
    db = FakeDb(task)
    with model_call_scope(db, task=task, attempt=Attempt(), node_name="planner"):
        result = LocalModelGateway().chat("sensitive customer details")

    assert result
    assert task.model_budget_usage["calls"] == 1
    assert len(db.records) == 1
    record = db.records[0]
    assert record.node_name == "planner"
    assert not hasattr(record, "prompt")
    assert not hasattr(record, "response")


def test_budget_exhaustion_stops_before_provider_call() -> None:
    task = Task()
    task.model_budget_usage = {"calls": 1, "calls_by_node": {"planner": 1}}
    db = FakeDb(task)

    with model_call_scope(db, task=task, attempt=Attempt(), node_name="planner"):
        with pytest.raises(ModelBudgetExceeded, match="budget exhausted"):
            reserve_model_call(provider="local", model_name="local-simulator")

    assert db.records == []


def test_prompt_token_and_repair_budgets_are_enforced_before_call() -> None:
    task = Task()
    task.model_budget_snapshot = {
        "max_calls": 3,
        "max_calls_per_node": 3,
        "max_total_tokens": 4,
        "max_cost": "1.00",
        "max_repairs": 0,
    }
    task.model_budget_usage = {"calls": 0, "tokens": 0, "cost": "0", "repairs": 0}
    db = FakeDb(task)

    with model_call_scope(db, task=task, attempt=Attempt(), node_name="data"):
        with pytest.raises(ModelBudgetExceeded, match="token budget"):
            reserve_model_call(
                provider="local",
                model_name="local-simulator",
                estimated_prompt_tokens=5,
            )
        with model_node_scope("data", is_repair=True):
            with pytest.raises(ModelBudgetExceeded, match="repair budget"):
                reserve_model_call(provider="local", model_name="local-simulator")


def test_transport_failure_keeps_reserved_prompt_tokens_charged() -> None:
    task = Task()
    db = FakeDb(task)
    with model_call_scope(db, task=task, attempt=Attempt(), node_name="planner"):
        scope = reserve_model_call(
            provider="local", model_name="local-simulator", estimated_prompt_tokens=12
        )
        record_model_call(
            scope,
            provider="local",
            model_name="local-simulator",
            result_category="retryable_error",
            error_code="provider_temporary_error",
        )

    assert task.model_budget_usage["tokens"] == 12
