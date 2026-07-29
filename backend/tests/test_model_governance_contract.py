from app.models.analysis_task import AnalysisTask
from app.models.model_call_record import ModelCallRecord


def test_task_model_governance_snapshots_have_safe_defaults() -> None:
    task = AnalysisTask(user_id=1, question="销售额", status="queued", stage="queued")

    policy = AnalysisTask.__table__.c.model_policy_snapshot.default.arg(None)
    budget = AnalysisTask.__table__.c.model_budget_snapshot.default.arg(None)
    usage = AnalysisTask.__table__.c.model_budget_usage.default.arg(None)

    assert policy["fallback_models"] == []
    assert policy["max_attempts"] == 3
    assert budget["max_calls_per_node"] <= budget["max_calls"]
    assert usage == {
        "calls": 0,
        "tokens": 0,
        "cost": "0.00",
        "repairs": 0,
        "calls_by_node": {},
    }
    assert task.question == "销售额"


def test_model_call_audit_never_has_raw_prompt_or_response_columns() -> None:
    columns = set(ModelCallRecord.__table__.c.keys())

    assert {"task_id", "execution_attempt_id", "node_name", "model_name"} <= columns
    assert {
        "prompt",
        "response",
        "system_prompt",
        "raw_request",
        "raw_response",
    }.isdisjoint(columns)
