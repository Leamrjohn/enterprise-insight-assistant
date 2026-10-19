from datetime import datetime, timezone

import pytest
from app.core.gateway.local import LocalModelGateway
from app.modules.workflow.model_call import ModelCallRecord
from app.modules.runtime.model_governance import (
    ModelBudgetExceeded,
    estimate_chat_prompt_tokens,
    model_call_scope,
    model_node_scope,
    record_model_call,
    reserve_local_resource_call,
    reserve_model_call,
)


class FakeDb:
    def __init__(self, task) -> None:
        self.task = task
        self.records = []
        self.commits = 0

    def get(self, model, identity, **kwargs):
        if model is ModelCallRecord:
            return self.records[0] if self.records else None
        return self.task

    def add(self, record) -> None:
        self.records.append(record)

    def commit(self) -> None:
        self.commits += 1

    def refresh(self, value) -> None:
        return None

    def scalar(self, statement):
        return datetime(2040, 1, 1, tzinfo=timezone.utc)


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


def test_chat_reservation_includes_system_user_and_message_framing() -> None:
    assert estimate_chat_prompt_tokens(len, "user", "system") == 18
    assert estimate_chat_prompt_tokens(len, "user", None) == 8


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
    assert record.prompt_template_id.startswith("system-sha256:")
    assert len(record.prompt_hash) == 64
    assert record.model_parameters == {"json_mode": False}
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


def test_output_reservation_stops_a_call_before_it_can_exceed_total_budget() -> None:
    task = Task()
    task.model_budget_snapshot = {
        "max_calls": 3,
        "max_calls_per_node": 3,
        "max_total_tokens": 7,
        "max_cost": "1.00",
        "max_repairs": 2,
    }
    task.model_budget_usage = {"calls": 0, "tokens": 0, "cost": "0", "repairs": 0}
    db = FakeDb(task)

    with (
        model_call_scope(db, task=task, attempt=Attempt(), node_name="planner"),
        pytest.raises(ModelBudgetExceeded, match="token budget"),
    ):
        reserve_model_call(
            provider="local",
            model_name="local-simulator",
            estimated_prompt_tokens=3,
            reserved_completion_tokens=5,
        )

    assert task.model_budget_usage["calls"] == 0
    assert task.model_budget_usage["tokens"] == 0


def test_actual_completion_reconciles_the_pre_reserved_output_allowance() -> None:
    task = Task()
    db = FakeDb(task)
    with model_call_scope(db, task=task, attempt=Attempt(), node_name="planner"):
        scope = reserve_model_call(
            provider="local",
            model_name="local-simulator",
            estimated_prompt_tokens=12,
            reserved_completion_tokens=20,
        )
        record_model_call(
            scope,
            provider="local",
            model_name="local-simulator",
            prompt_tokens=10,
            completion_tokens=7,
            result_category="success",
        )

    assert task.model_budget_usage["tokens"] == 17
    assert db.records[0].settled_at == datetime(2040, 1, 1, tzinfo=timezone.utc)


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


def test_paid_call_has_one_pre_request_id_and_settles_from_frozen_price() -> None:
    task = Task()
    task.model_policy_snapshot = {
        "model_pricing": {
            "version": "prices-2026-10-10",
            "entries": [
                {
                    "price_id": "openai-gpt-json",
                    "provider": "openai",
                    "model_name": "gpt-test",
                    "parameters": {"json_mode": True},
                    "prompt_per_1k": "0.01",
                    "completion_per_1k": "0.02",
                },
                {
                    "price_id": "deepseek-chat",
                    "provider": "deepseek",
                    "model_name": "deepseek-test",
                    "parameters": {},
                    "prompt_per_1k": "0.03",
                    "completion_per_1k": "0.04",
                },
            ],
        }
    }
    db = FakeDb(task)

    with model_call_scope(db, task=task, attempt=Attempt(), node_name="planner"):
        scope = reserve_model_call(
            provider="openai",
            model_name="gpt-test",
            estimated_prompt_tokens=20,
            reserved_completion_tokens=30,
            pricing_parameters={"json_mode": True},
        )
        assert scope is not None
        assert scope.model_call_id
        assert len(db.records) == 1
        assert db.records[0].billing_status == "reserved"
        assert db.records[0].pricing_key == "openai-gpt-json"
        record_model_call(
            scope,
            provider="openai",
            model_name="gpt-test",
            prompt_tokens=10,
            completion_tokens=5,
            result_category="success",
            model_parameters={"json_mode": True},
        )
        record_model_call(
            scope,
            provider="openai",
            model_name="gpt-test",
            prompt_tokens=10,
            completion_tokens=5,
            result_category="success",
            model_parameters={"json_mode": True},
        )

    record = db.records[0]
    assert len(db.records) == 1
    assert record.billing_status == "settled"
    assert str(record.cost) == "0.00020"
    assert task.model_budget_usage["tokens"] == 15
    assert task.model_budget_usage["cost"] == "0.00020"
    assert task.model_budget_usage["reserved_cost"] == "0"


def test_timeout_is_unknown_not_a_zero_cost_settlement() -> None:
    task = Task()
    task.model_policy_snapshot = {
        "model_pricing": {
            "version": "prices-2026-10-10",
            "entries": [
                {
                    "price_id": "deepseek-chat",
                    "provider": "deepseek",
                    "model_name": "deepseek-test",
                    "parameters": {},
                    "prompt_per_1k": "0.03",
                    "completion_per_1k": "0.04",
                }
            ],
        }
    }
    db = FakeDb(task)

    with model_call_scope(db, task=task, attempt=Attempt(), node_name="planner"):
        scope = reserve_model_call(
            provider="deepseek",
            model_name="deepseek-test",
            estimated_prompt_tokens=20,
            reserved_completion_tokens=30,
        )
        record_model_call(
            scope,
            provider="deepseek",
            model_name="deepseek-test",
            result_category="retryable_error",
            error_code="provider_timeout",
        )

    record = db.records[0]
    assert record.billing_status == "unknown"
    assert record.cost is None
    assert task.model_budget_usage["tokens"] == 50
    assert task.model_budget_usage["cost"] == "0.00"
    assert task.model_budget_usage["reserved_cost"] == "0.0018"
    assert task.model_budget_usage["unknown_cost_calls"] == 1


def test_local_rerank_resource_has_a_durable_non_monetary_settlement() -> None:
    task = Task()
    db = FakeDb(task)

    with model_call_scope(db, task=task, attempt=Attempt(), node_name="knowledge"):
        scope = reserve_local_resource_call(
            resource_kind="rerank",
            model_name="local-reranker",
            resource_usage={"candidate_count": 10, "question_characters": 12},
        )
        record_model_call(
            scope,
            provider="local",
            model_name="local-reranker",
            duration_ms=17.4,
            result_category="success",
            resource_usage={"candidate_count": 10, "question_characters": 12},
        )

    record = db.records[0]
    assert record.model_call_id
    assert record.charge_kind == "local_resource"
    assert record.billing_status == "settled"
    assert record.cost == 0
    assert record.resource_usage == {"candidate_count": 10, "question_characters": 12}
    assert task.model_budget_usage["calls"] == 0
