from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from app.modules.organizations.models import Company
from app.modules.workflow.models import AnalysisTask
from scripts.render_task_trace import load_trace, render_trace_html


def test_trace_html_excludes_payloads_and_escapes_audit_metadata() -> None:
    now = datetime(2026, 10, 9, tzinfo=UTC)
    task = SimpleNamespace(
        id=12,
        company_id=4,
        status="partial",
        stage="completed",
        created_at=now,
        completed_at=now,
        duration_ms=20,
        question="do not publish this question",
        clarification_status="waiting",
        clarification_missing_fields=["time_range", "region", "do not publish"],
    )
    attempt = SimpleNamespace(
        id=8,
        status="partial",
        retry_number=1,
        workflow_version="v1",
        started_at=now,
        finished_at=now,
    )
    event = SimpleNamespace(
        created_at=now,
        execution_attempt_id=8,
        event_type="node_completed",
        node_name="reviewer_node",
        tool_name=None,
        status="done",
        error_code="<safe-code>",
        duration_ms=5,
        details={"sql": "SELECT secret"},
    )
    model_call = SimpleNamespace(
        created_at=now,
        execution_attempt_id=8,
        node_name="reviewer",
        provider="test",
        model_name="model",
        result_category="success",
        error_code=None,
        duration_ms=6,
        prompt_tokens=3,
        completion_tokens=2,
        cost="0.01",
        prompt="do not publish prompt",
    )
    tool_call = SimpleNamespace(
        created_at=now,
        execution_attempt_id=8,
        tool_name="rag_search",
        status="succeeded",
        error_code=None,
        duration_ms=7,
        metadata_json={"result": "do not publish result"},
    )

    html = render_trace_html(
        task=task,
        attempts=[attempt],
        events=[event],
        model_calls=[model_call],
        tool_calls=[tool_call],
    )

    assert "do not publish" not in html
    assert "SELECT secret" not in html
    assert "Clarification status" in html
    assert "time_range, region" in html
    assert "&lt;safe-code&gt;" in html
    assert "tokens=5; cost=0.01" in html


def test_trace_loader_rejects_a_task_outside_the_requested_company(
    db_session, test_user
) -> None:
    owner = Company(name="trace-owner")
    other = Company(name="trace-other")
    db_session.add_all([owner, other])
    db_session.flush()
    task = AnalysisTask(
        user_id=test_user.id,
        company_id=owner.id,
        question="private task question",
        status="completed",
        stage="completed",
    )
    db_session.add(task)
    db_session.flush()

    with pytest.raises(ValueError, match="requested company scope"):
        load_trace(db_session, company_id=other.id, task_id=task.id)

    loaded_task, *_ = load_trace(db_session, company_id=owner.id, task_id=task.id)
    assert loaded_task.id == task.id
