from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from app.modules.analysis.agent_protocol import AgentInput
from app.modules.analysis.planner.planner_agent import PlannerAgent
from app.modules.runtime.model_governance import ModelBudgetExceeded
from app.modules.workflow import tasks


def failing_planner(error):
    service = SimpleNamespace(model_attempts=1, decide=MagicMock(side_effect=error))
    return PlannerAgent(planning_service=service)


def test_planner_preserves_budget_exception_identity():
    error = ModelBudgetExceeded("offline budget exhausted")
    with pytest.raises(ModelBudgetExceeded) as caught:
        failing_planner(error).run(AgentInput(question="test", user_id=1))
    assert caught.value is error


def test_planner_keeps_ordinary_exception_classification():
    result = failing_planner(ValueError("offline invalid value")).run(
        AgentInput(question="test", user_id=1)
    )
    assert result.success is False
    assert result.error_code == "planner_unexpected_error"


def test_worker_handles_planner_budget_without_retry_or_publish(monkeypatch):
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = []
    db.query.return_value.filter.return_value.first.return_value = None
    record = SimpleNamespace(
        id=1,
        user_id=1,
        company_id=112,
        request_id=None,
        question="test",
        result_data={},
        context_snapshot={},
        data_source_id=None,
        schema_snapshot_id=None,
    )
    execution = SimpleNamespace(
        task=record,
        attempt=SimpleNamespace(id=1, task_id=1),
        resume_next_node=None,
        resume_state=None,
    )
    monkeypatch.setattr(tasks, "SessionLocal", lambda: db)
    monkeypatch.setattr(tasks, "_claim_task", lambda *a, **kw: execution)
    monkeypatch.setattr(tasks, "set_tenant_scope", MagicMock())
    monkeypatch.setattr(tasks, "_stop_if_cancelled", lambda *a: False)
    monkeypatch.setattr(tasks, "_sync_assistant_message", MagicMock())
    monkeypatch.setattr(
        tasks,
        "build_task_attachment_context",
        lambda *a, **kw: SimpleNamespace(selection_manifest={}, planner_payload={}),
    )
    monkeypatch.setattr(tasks, "select_planner_memories", lambda *a, **kw: ([], {}))
    monkeypatch.setattr(tasks, "append_workflow_event", MagicMock())
    monkeypatch.setattr(tasks, "model_call_scope", lambda *a, **kw: nullcontext())
    monkeypatch.setattr(tasks, "_maintain_execution_lease", lambda *a: nullcontext())
    monkeypatch.setattr(tasks, "_duration_ms", lambda *a: 1)
    transition = MagicMock(return_value=record)
    monkeypatch.setattr(tasks, "transition_execution", transition)
    publish = MagicMock()
    monkeypatch.setattr(tasks, "_save_workflow_result", publish)
    retry = MagicMock(side_effect=AssertionError("budget exhaustion must not retry"))
    monkeypatch.setattr(tasks.process_analysis_task, "retry", retry)
    planner = failing_planner(ModelBudgetExceeded("offline budget exhausted"))

    def run(question, user_id, **kwargs):
        return planner.run(AgentInput(question=question, user_id=user_id))

    monkeypatch.setattr(tasks, "run_analysis", run)
    tasks.process_analysis_task.run(1)
    assert transition.call_count == 1
    assert transition.call_args.kwargs["task_status"] == "partial"
    assert transition.call_args.kwargs["error_type"] == "model_budget_exhausted"
    assert (
        transition.call_args.kwargs["recovery_instruction"]
        == "model_budget_exhausted_stop"
    )
    assert record.result_data["type"] == "model_budget_exhausted"
    assert "report" not in record.result_data
    publish.assert_not_called()
    retry.assert_not_called()
    db.close.assert_called_once()
