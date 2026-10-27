from datetime import date, datetime, timedelta, timezone

import pytest
from app.db.session import set_tenant_scope
from app.modules.analysis.tool_protocol import Tool, ToolInput, ToolOutput
from app.modules.documents.models import Documents
from app.modules.evaluation.observation import observation_from_runtime_tool_rejection
from app.modules.identity.models import User
from app.modules.knowledge.mcp_adapter import (
    McpEvidenceReadTool,
    create_evidence_mcp_server,
    document_scope_sha256,
)
from app.modules.organizations.models import Company, CompanyMember
from app.modules.runtime.tool_runtime import ToolRuntime, ToolRuntimeContext
from app.modules.workflow.audit.events_models import WorkflowEvent
from app.modules.workflow.audit.tool_call import ToolCallRecord
from app.modules.workflow.lifecycle.execution_attempt import TaskExecutionAttempt
from app.modules.workflow.models import AnalysisTask


class _FakeRagTool(Tool):
    def __init__(self) -> None:
        self.inputs: list[ToolInput] = []

    @property
    def name(self) -> str:
        return "rag_search"

    @property
    def description(self) -> str:
        return "test rag tool"

    def execute(self, input: ToolInput) -> ToolOutput:
        self.inputs.append(input)
        return ToolOutput(success=True, data={"status": "ready", "rows": []})


class _FaultyRagTool(_FakeRagTool):
    def __init__(self, failure: Exception | object) -> None:
        super().__init__()
        self._failure = failure

    def execute(self, input: ToolInput) -> ToolOutput:
        self.inputs.append(input)
        if isinstance(self._failure, Exception):
            raise self._failure
        return self._failure  # type: ignore[return-value]


class _FakeSqlTool(Tool):
    def __init__(self) -> None:
        self.inputs: list[ToolInput] = []

    @property
    def name(self) -> str:
        return "sql_query"

    @property
    def description(self) -> str:
        return "test sql tool"

    def execute(self, input: ToolInput) -> ToolOutput:
        self.inputs.append(input)
        return ToolOutput(success=True, data={"status": "ready", "rows": []})


class _FakeTemplateTool(Tool):
    def __init__(self) -> None:
        self.inputs: list[ToolInput] = []

    @property
    def name(self) -> str:
        return "template_query"

    @property
    def description(self) -> str:
        return "test registered query tool"

    def execute(self, input: ToolInput) -> ToolOutput:
        self.inputs.append(input)
        return ToolOutput(success=True, data={"status": "ready", "rows": []})


class _UnknownTool(Tool):
    def __init__(self) -> None:
        self.inputs: list[ToolInput] = []

    @property
    def name(self) -> str:
        return "unknown_tool"

    @property
    def description(self) -> str:
        return "unregistered test tool"

    def execute(self, input: ToolInput) -> ToolOutput:
        self.inputs.append(input)
        return ToolOutput(success=True, data={"status": "ready", "rows": []})


def _runtime(db_session):
    user = User(name="runtime-user", api_key="runtime-key")
    company = Company(name="runtime-company")
    db_session.add_all([user, company])
    db_session.flush()
    set_tenant_scope(db_session, company.id)
    db_session.add(
        CompanyMember(company_id=company.id, user_id=user.id, role="analyst")
    )
    db_session.add(
        Documents(
            id=11,
            uploaded_by_user_id=user.id,
            company_id=company.id,
            name="runtime-scope.txt",
            source="test",
            min_view_role="any",
        )
    )
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


def test_new_task_freezes_default_tool_timeout_policy(db_session) -> None:
    _, attempt, _company = _runtime(db_session)
    task = db_session.get(AnalysisTask, attempt.task_id)

    assert task.tool_policy_snapshot["sql_statement_timeout_ms"] == 10_000
    assert task.tool_policy_snapshot["rag_database_timeout_ms"] == 10_000


@pytest.mark.parametrize(
    "failure", [None, "disabled", "revoked", "company", "scope", "policy", "database"]
)
def test_wrapped_empty_scope_is_insufficient_only_after_authorization(
    db_session, monkeypatch, failure
):
    _, attempt, company = _runtime(db_session)
    task = db_session.get(AnalysisTask, attempt.task_id)
    runtime = ToolRuntime(
        db=db_session,
        attempt=attempt,
        context=ToolRuntimeContext(
            task_id=task.id,
            company_id=company.id,
            allowed_document_ids=frozenset({11}) if failure == "scope" else frozenset(),
        ),
    )
    if failure == "disabled":
        db_session.get(User, task.user_id).is_active = False
    if failure == "revoked":
        db_session.query(CompanyMember).filter_by(company_id=company.id).delete()
    if failure == "policy":
        task.tool_policy_snapshot = {
            **task.tool_policy_snapshot,
            "allowed_tools": ["sql_query"],
        }
    db_session.flush()
    tool = _FakeRagTool()
    wrapped = runtime.wrap(tool)
    request = ToolInput(
        parameters={
            "question": "private question",
            "company_id": company.id + 1 if failure == "company" else company.id,
            "document_ids": [],
        }
    )
    if failure == "database":

        def unavailable(*args, **kwargs):
            raise RuntimeError("authorization unavailable")

        monkeypatch.setattr(runtime, "_validate_current_authorization", unavailable)
        with pytest.raises(RuntimeError, match="authorization unavailable"):
            wrapped.execute(request)
    else:
        result = wrapped.execute(request)
        assert result.success is (failure is None)
        if failure is None:
            assert result.data["status"] == "insufficient_evidence"
            assert result.data["evidences"] == []
            assert db_session.query(ToolCallRecord).count() == 0
            event = (
                db_session.query(WorkflowEvent)
                .filter_by(event_type="knowledge_scope_empty")
                .one()
            )
            assert event.details == {"reason_code": "frozen_document_scope_empty"}
    assert tool.inputs == []
    assert task.tool_budget_usage.get("calls", 0) == 0


@pytest.mark.parametrize(
    "parameters", [{}, {"document_ids": None}, {"document_ids": [11]}]
)
def test_empty_scope_adapter_does_not_accept_missing_or_nonempty_request(
    db_session, parameters
):
    _, attempt, company = _runtime(db_session)
    runtime = ToolRuntime(
        db=db_session,
        attempt=attempt,
        context=ToolRuntimeContext(
            task_id=attempt.task_id,
            company_id=company.id,
            allowed_document_ids=frozenset(),
        ),
    )
    tool = _FakeRagTool()
    result = runtime.wrap(tool).execute(
        ToolInput(parameters={"company_id": company.id, "question": "q", **parameters})
    )
    assert result.success is False
    assert result.error_code == "tool_document_scope_denied"
    assert tool.inputs == []


def test_empty_scope_reaches_insufficient_terminal_without_search_or_model(
    db_session, monkeypatch
):
    from app.modules.knowledge.tool import RAGTool
    from app.modules.workflow.orchestration.nodes import (
        knowledge_node,
        reviewer_node,
        smart_router_node,
    )

    _, attempt, company = _runtime(db_session)
    task = db_session.get(AnalysisTask, attempt.task_id)
    runtime = ToolRuntime(
        db=db_session,
        attempt=attempt,
        context=ToolRuntimeContext(
            task_id=task.id, company_id=company.id, allowed_document_ids=frozenset()
        ),
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("empty scope must not search or call a model")

    monkeypatch.setattr(RAGTool, "execute", forbidden)
    monkeypatch.setattr("app.modules.knowledge.agent.get_model_gateway", forbidden)
    monkeypatch.setattr(
        "app.modules.reporting.semantic_review_service.get_model_gateway", forbidden
    )
    state = {
        "question": "有哪些资料？",
        "user_id": task.user_id,
        "company_id": company.id,
        "document_ids": [],
        "tool_runtime": runtime,
        "plan": {"route": "knowledge_only", "intent": {"kind": "document_question"}},
        "data_result": None,
    }
    state.update(knowledge_node(state))
    assert state["knowledge_result"]["status"] == "insufficient_evidence"
    state.update(reviewer_node(state))
    assert state["review_result"]["review_status"] == "partial"
    state.update(smart_router_node(state))
    assert state["terminal_result"]["outcome"] == "insufficient_evidence"
    assert db_session.query(ToolCallRecord).count() == 0


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
    assert record.tool_contract_version == "rag_search/v2"
    assert record.duration_ms is not None
    assert "secret document text" not in str(record.metadata_json)


@pytest.mark.parametrize(
    "failure",
    [TimeoutError("private-driver-detail-must-not-persist"), {"status": "ready"}],
)
def test_tool_runtime_degrades_exception_and_malformed_result_without_leaking_details(
    db_session, failure
) -> None:
    runtime, attempt, company = _runtime(db_session)

    result = runtime.execute(
        _FaultyRagTool(failure),
        ToolInput(
            parameters={
                "company_id": company.id,
                "document_ids": [11],
                "question": "secret document text must not be stored",
            }
        ),
    )

    assert result.success is False
    assert result.error_code == "tool_runtime_unexpected_error"
    events = (
        db_session.query(WorkflowEvent)
        .filter(WorkflowEvent.execution_attempt_id == attempt.id)
        .order_by(WorkflowEvent.sequence)
        .all()
    )
    assert [event.event_type for event in events] == ["tool_started", "tool_failed"]
    assert "secret document text" not in str(events)
    record = (
        db_session.query(ToolCallRecord)
        .filter(ToolCallRecord.execution_attempt_id == attempt.id)
        .one()
    )
    assert record.status == "failed"
    assert record.error_code == "tool_runtime_unexpected_error"
    persisted = repr([vars(event) for event in events] + [vars(record)])
    assert "private-driver-detail-must-not-persist" not in persisted
    assert "secret document text" not in persisted
    assert "private-driver-detail-must-not-persist" not in repr(result)


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
    observation = observation_from_runtime_tool_rejection(
        db_session,
        case_id="runtime-document-scope-denial",
        task_id=attempt.task_id,
    )
    assert observation.runtime_tool_denial_status == "passed"
    assert observation.tool_execution_prevented_status == "passed"
    assert observation.actual_tool_denial_codes == ["tool_document_scope_denied"]


def test_tool_runtime_rejects_the_same_illegal_scope_before_local_or_mcp_call(
    db_session,
) -> None:
    runtime, _attempt, company = _runtime(db_session)
    illegal_input = ToolInput(
        parameters={"company_id": company.id, "document_ids": [12], "question": "q"}
    )
    local_reader = _FakeRagTool()
    mcp_reader = _FakeRagTool()

    local_result = runtime.execute(local_reader, illegal_input)
    mcp_result = runtime.execute(
        McpEvidenceReadTool(create_evidence_mcp_server(mcp_reader)), illegal_input
    )

    assert local_result.error_code == "tool_document_scope_denied"
    assert mcp_result.error_code == local_result.error_code
    assert local_reader.inputs == []
    assert mcp_reader.inputs == []


def test_tool_runtime_denies_missing_document_scope(db_session) -> None:
    runtime, _attempt, company = _runtime(db_session)

    result = runtime.execute(
        _FakeRagTool(),
        ToolInput(parameters={"company_id": company.id, "question": "q"}),
    )

    assert result.success is False
    assert result.error_code == "tool_document_scope_denied"


def test_tool_runtime_denies_an_empty_frozen_document_scope(db_session) -> None:
    runtime, attempt, company = _runtime(db_session)
    runtime = ToolRuntime(
        db=db_session,
        attempt=attempt,
        context=ToolRuntimeContext(
            task_id=attempt.task_id,
            company_id=company.id,
            allowed_document_ids=frozenset(),
        ),
    )
    tool = _FakeRagTool()

    result = runtime.execute(
        tool,
        ToolInput(
            parameters={"company_id": company.id, "document_ids": [], "question": "q"}
        ),
    )

    assert result.success is False
    assert result.error_code == "tool_document_scope_denied"
    assert tool.inputs == []


def test_tool_runtime_denies_an_unknown_tool_before_authorization_or_execution(
    db_session,
) -> None:
    runtime, attempt, _company = _runtime(db_session)
    tool = _UnknownTool()

    result = runtime.execute(tool, ToolInput(parameters={"ignored": "value"}))

    assert result.error_code == "tool_not_allowlisted"
    assert tool.inputs == []
    record = (
        db_session.query(ToolCallRecord)
        .filter(ToolCallRecord.execution_attempt_id == attempt.id)
        .one()
    )
    assert record.status == "denied"
    assert record.error_code == "tool_not_allowlisted"


def test_tool_runtime_denies_revoked_user_before_tool_execution(db_session) -> None:
    runtime, attempt, company = _runtime(db_session)
    task = db_session.get(AnalysisTask, attempt.task_id)
    membership = (
        db_session.query(CompanyMember)
        .filter(
            CompanyMember.company_id == company.id,
            CompanyMember.user_id == task.user_id,
        )
        .one()
    )
    membership.status = "disabled"
    db_session.commit()
    tool = _FakeRagTool()

    result = runtime.execute(
        tool,
        ToolInput(
            parameters={"company_id": company.id, "document_ids": [11], "question": "q"}
        ),
    )

    assert result.error_code == "tool_current_authorization_denied"
    assert tool.inputs == []
    event = (
        db_session.query(WorkflowEvent)
        .filter(WorkflowEvent.execution_attempt_id == attempt.id)
        .one()
    )
    assert event.event_type == "tool_denied"
    assert event.details == {}


def test_tool_runtime_denies_revoked_user_before_mcp_evidence_read(
    db_session,
) -> None:
    runtime, attempt, company = _runtime(db_session)
    task = db_session.get(AnalysisTask, attempt.task_id)
    membership = (
        db_session.query(CompanyMember)
        .filter(
            CompanyMember.company_id == company.id,
            CompanyMember.user_id == task.user_id,
        )
        .one()
    )
    membership.status = "disabled"
    db_session.commit()
    reader = _FakeRagTool()
    mcp_tool = McpEvidenceReadTool(create_evidence_mcp_server(reader))

    result = runtime.execute(
        mcp_tool,
        ToolInput(
            parameters={"company_id": company.id, "document_ids": [11], "question": "q"}
        ),
    )

    assert result.error_code == "tool_current_authorization_denied"
    assert reader.inputs == []


def test_tool_runtime_denies_viewer_before_sql_execution(db_session) -> None:
    runtime, attempt, company = _runtime(db_session)
    task = db_session.get(AnalysisTask, attempt.task_id)
    membership = (
        db_session.query(CompanyMember)
        .filter(
            CompanyMember.company_id == company.id,
            CompanyMember.user_id == task.user_id,
        )
        .one()
    )
    membership.role = "viewer"
    db_session.commit()
    tool = _FakeSqlTool()

    result = runtime.execute(tool, ToolInput(parameters={"sql": "SELECT 1"}))

    assert result.error_code == "tool_current_authorization_denied"
    assert tool.inputs == []


def test_tool_runtime_denies_document_that_is_no_longer_visible(db_session) -> None:
    runtime, attempt, company = _runtime(db_session)
    document = db_session.get(Documents, 11)
    document.min_view_role = "owner"
    db_session.commit()
    tool = _FakeRagTool()

    result = runtime.execute(
        tool,
        ToolInput(
            parameters={"company_id": company.id, "document_ids": [11], "question": "q"}
        ),
    )

    assert result.error_code == "tool_document_current_authorization_denied"
    assert tool.inputs == []
    event = (
        db_session.query(WorkflowEvent)
        .filter(WorkflowEvent.execution_attempt_id == attempt.id)
        .one()
    )
    assert event.event_type == "tool_denied"


def test_tool_runtime_rejects_invalid_rag_schema_before_execution(db_session) -> None:
    runtime, attempt, company = _runtime(db_session)
    tool = _FakeRagTool()

    result = runtime.execute(
        tool,
        ToolInput(
            parameters={
                "company_id": company.id,
                "document_ids": "not-a-list",
                "question": "q",
            }
        ),
    )

    assert result.success is False
    assert result.error_code == "tool_input_schema_invalid"
    assert tool.inputs == []
    event = (
        db_session.query(WorkflowEvent)
        .filter(WorkflowEvent.execution_attempt_id == attempt.id)
        .one()
    )
    assert event.event_type == "tool_denied"
    assert event.details == {
        "parameter_keys": ["company_id", "document_ids", "question"],
        "schema": "rag_search/v1",
    }


def test_tool_runtime_injects_frozen_sql_timeout_after_dropping_user_value(
    db_session,
) -> None:
    runtime, attempt, _company = _runtime(db_session)
    task = db_session.get(AnalysisTask, attempt.task_id)
    task.tool_policy_snapshot = {
        "allowed_tools": ["rag_search", "sql_query", "template_query"],
        "require_company_scope": True,
        "require_frozen_document_scope": True,
        "sql_statement_timeout_ms": 321,
    }
    db_session.commit()
    tool = _FakeSqlTool()

    result = runtime.execute(
        tool,
        ToolInput(
            parameters={
                "sql": "SELECT 1",
                "_runtime_timeout_ms": 60_000,
            }
        ),
    )

    assert result.success is True
    assert tool.inputs[0].parameters == {
        "sql": "SELECT 1",
        "_runtime_timeout_ms": 321,
    }
    event = (
        db_session.query(WorkflowEvent)
        .filter(WorkflowEvent.execution_attempt_id == attempt.id)
        .order_by(WorkflowEvent.sequence)
        .first()
    )
    assert event.details == {"parameter_keys": ["sql"]}


def test_tool_runtime_injects_frozen_rag_database_timeout(
    db_session,
) -> None:
    runtime, attempt, company = _runtime(db_session)
    task = db_session.get(AnalysisTask, attempt.task_id)
    task.tool_policy_snapshot = {
        "allowed_tools": ["rag_search", "sql_query", "template_query"],
        "require_company_scope": True,
        "require_frozen_document_scope": True,
        "rag_database_timeout_ms": 321,
    }
    db_session.commit()
    tool = _FakeRagTool()

    result = runtime.execute(
        tool,
        ToolInput(
            parameters={
                "company_id": company.id,
                "document_ids": [11],
                "question": "q",
                "_runtime_database_timeout_ms": 60_000,
            }
        ),
    )

    assert result.success is True
    parameters = tool.inputs[0].parameters
    assert parameters == {
        "company_id": company.id,
        "document_ids": [11],
        "question": "q",
        "_runtime_database_timeout_ms": 321,
        "_runtime_mcp_context": {
            "version": "agent-evidence-runtime/v1",
            "tool_contract_version": "evidence_read/v1",
            "task_id": attempt.task_id,
            "execution_id": "runtime-execution",
            "actor_id": db_session.get(AnalysisTask, attempt.task_id).user_id,
            "actor_auth_version": 0,
            "authorized_role": "analyst",
            "company_id": company.id,
            "document_scope_sha256": document_scope_sha256(company.id, [11]),
        },
    }


def test_tool_runtime_validates_registered_query_schema(db_session) -> None:
    runtime, _attempt, _company = _runtime(db_session)
    tool = _FakeTemplateTool()

    result = runtime.execute(
        tool,
        ToolInput(
            parameters={
                "query_id": "regional_revenue_comparison",
                "current_month": "2025-08-01",
                "comparison_month": "2025-07-01",
                "unexpected": "discarded",
            }
        ),
    )

    assert result.success is True
    assert tool.inputs[0].parameters == {
        "query_id": "regional_revenue_comparison",
        "region": None,
        "current_month": date(2025, 8, 1),
        "comparison_month": date(2025, 7, 1),
        "limit": 20,
    }


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
        ToolInput(
            parameters={"company_id": company.id, "document_ids": [11], "question": "q"}
        ),
    )

    assert result.error_code == "tool_budget_exhausted"
    assert db_session.query(ToolCallRecord).one().status == "denied"
