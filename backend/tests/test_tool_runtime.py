from datetime import datetime, timedelta, timezone

from app.models.analysis_task import AnalysisTask
from app.models.company import Company
from app.models.task_execution_attempt import TaskExecutionAttempt
from app.models.user import User
from app.models.workflow_event import WorkflowEvent
from app.models.tool_call_record import ToolCallRecord
from app.services.tool_runtime import ToolRuntime, ToolRuntimeContext
from app.tools.protocol import Tool, ToolInput, ToolOutput


class _FakeRagTool(Tool):
    @property
    def name(self) -> str:
        return "rag_search"

    @property
    def description(self) -> str:
        return "test rag tool"

    def execute(self, input: ToolInput) -> ToolOutput:
        return ToolOutput(success=True, data={"status": "ready", "rows": []})


def _runtime(db_session):
    user = User(name="runtime-user", api_key="runtime-key")
    company = Company(name="runtime-company")
    db_session.add_all([user, company])
    db_session.flush()
    task = AnalysisTask(
        user_id=user.id,
        company_id=company.id,
        question="为什么下降？",
        status="running",
        stage="retrieving_knowledge",
        active_execution_id="runtime-execution",
    )
    db_session.add(task)
    db_session.flush()
    attempt = TaskExecutionAttempt(
        task_id=task.id,
        execution_id="runtime-execution",
        lease_expires_at=datetime.now(timezone.utc) + timedelta(minutes=1),
    )
    db_session.add(attempt)
    db_session.flush()
    return (
        ToolRuntime(
            db=db_session,
            attempt=attempt,
            context=ToolRuntimeContext(
                task_id=task.id,
                company_id=company.id,
                allowed_document_ids=frozenset({11}),
            ),
        ),
        attempt,
        company,
    )


def test_tool_runtime_records_redacted_start_and_completion_events(db_session) -> None:
    runtime, attempt, company = _runtime(db_session)

    result = runtime.execute(
        _FakeRagTool(),
        ToolInput(
            parameters={
                "company_id": company.id,
                "document_ids": [11],
                "question": "secret document text must not be stored",
            }
        ),
    )

    assert result.success is True
    events = (
        db_session.query(WorkflowEvent)
        .filter(WorkflowEvent.execution_attempt_id == attempt.id)
        .order_by(WorkflowEvent.sequence)
        .all()
    )
    assert [event.event_type for event in events] == ["tool_started", "tool_completed"]
    assert events[0].details == {
        "parameter_keys": ["company_id", "document_ids", "question"]
    }
    assert "secret document text" not in str(events)
    record = db_session.query(ToolCallRecord).one()
    assert record.status == "succeeded"
    assert record.duration_ms is not None
    assert "secret document text" not in str(record.metadata_json)


def test_tool_runtime_denies_document_ids_outside_frozen_scope(db_session) -> None:
    runtime, attempt, company = _runtime(db_session)

    result = runtime.execute(
        _FakeRagTool(),
        ToolInput(
            parameters={"company_id": company.id, "document_ids": [12], "question": "q"}
        ),
    )

    assert result.success is False
    assert result.error_code == "tool_document_scope_denied"
    event = (
        db_session.query(WorkflowEvent)
        .filter(WorkflowEvent.execution_attempt_id == attempt.id)
        .one()
    )
    assert event.event_type == "tool_denied"
    assert event.details == {}
    assert db_session.query(ToolCallRecord).one().status == "denied"


def test_tool_runtime_stops_before_call_when_task_budget_is_exhausted(
    db_session,
) -> None:
    runtime, attempt, company = _runtime(db_session)
    task = db_session.get(AnalysisTask, attempt.task_id)
    task.tool_budget_snapshot = {"max_calls": 1, "max_calls_per_tool": 1}
    task.tool_budget_usage = {"calls": 1, "calls_by_tool": {"rag_search": 1}}
    db_session.commit()

    result = runtime.execute(
        _FakeRagTool(),
        ToolInput(parameters={"company_id": company.id, "document_ids": [11]}),
    )

    assert result.error_code == "tool_budget_exhausted"
    assert db_session.query(ToolCallRecord).one().status == "denied"
