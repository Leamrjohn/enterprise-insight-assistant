from types import SimpleNamespace

from app.modules.runtime.model_governance import (
    model_call_scope,
    record_model_call,
    reserve_model_call,
)
from app.modules.workflow.model_call import ModelCallRecord
from app.modules.workflow.models import AnalysisTask


def test_paid_call_reservation_and_duplicate_settlement_are_durable(
    db_session, test_user
) -> None:
    task = AnalysisTask(
        user_id=test_user.id,
        question="test ledger",
        status="queued",
        stage="queued",
        model_policy_snapshot={
            "model_pricing": {
                "version": "test-prices-v1",
                "entries": [
                    {
                        "price_id": "test-price",
                        "provider": "openai",
                        "model_name": "test-model",
                        "parameters": {"json_mode": True},
                        "prompt_per_1k": "0.01",
                        "completion_per_1k": "0.02",
                    }
                ],
            }
        },
        model_budget_snapshot={
            "max_calls": 3,
            "max_calls_per_node": 3,
            "max_repairs": 1,
            "max_total_tokens": 1000,
            "max_cost": "1.00",
        },
        model_budget_usage={
            "calls": 0,
            "tokens": 0,
            "cost": "0.00",
            "reserved_cost": "0.00",
            "unknown_cost_calls": 0,
            "repairs": 0,
            "calls_by_node": {},
        },
    )
    db_session.add(task)
    db_session.commit()

    with model_call_scope(
        db_session,
        task=task,
        attempt=SimpleNamespace(id=None),
        node_name="planner",
    ):
        scope = reserve_model_call(
            provider="openai",
            model_name="test-model",
            estimated_prompt_tokens=20,
            reserved_completion_tokens=30,
            pricing_parameters={"json_mode": True},
        )
        assert scope is not None
        reserved = (
            db_session.query(ModelCallRecord)
            .filter(ModelCallRecord.model_call_id == scope.model_call_id)
            .one()
        )
        assert reserved.billing_status == "reserved"
        record_model_call(
            scope,
            provider="openai",
            model_name="test-model",
            prompt_tokens=10,
            completion_tokens=5,
            result_category="success",
            model_parameters={"json_mode": True},
        )
        record_model_call(
            scope,
            provider="openai",
            model_name="test-model",
            prompt_tokens=10,
            completion_tokens=5,
            result_category="success",
            model_parameters={"json_mode": True},
        )

    records = (
        db_session.query(ModelCallRecord)
        .filter(ModelCallRecord.task_id == task.id)
        .all()
    )
    db_session.refresh(task)
    assert len(records) == 1
    assert records[0].billing_status == "settled"
    assert str(records[0].cost) == "0.000200"
    assert task.model_budget_usage["cost"] == "0.00020"
    assert task.model_budget_usage["reserved_cost"] == "0"
