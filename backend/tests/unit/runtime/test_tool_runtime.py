from contextlib import nullcontext
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from time import monotonic, sleep

import pytest
from app.core.settings import get_settings
from app.db.session import set_tenant_scope
from app.modules.analysis.catalog.snapshot_catalog import SnapshotCatalog
from app.modules.analysis.data.sql_tool import SQLTool
from app.modules.analysis.tool_protocol import Tool, ToolInput, ToolOutput
from app.modules.documents.models import Documents
from app.modules.evaluation.observation import observation_from_runtime_tool_rejection
from app.modules.identity.models import User
from app.modules.organizations.models import (
    BusinessDataSource,
    Company,
    CompanyMember,
    SchemaSnapshot,
)
from app.modules.runtime import tool_runtime
from app.modules.runtime.model_governance import (
    ModelBudgetExceeded,
    ModelCallCancelled,
)
from app.modules.runtime.tool_runtime import ToolRuntime, ToolRuntimeContext
from app.modules.runtime.tools import catalog
from app.modules.runtime.tools.registry import ToolRegistry
from app.modules.workflow.audit.events_models import WorkflowEvent
from app.modules.workflow.audit.tool_call import ToolCallRecord
from app.modules.workflow.lifecycle.execution_attempt import TaskExecutionAttempt
from app.modules.workflow.models import AnalysisTask
from app.tool_service import server as server_module
from app.tool_service.server import (
    ServiceTool,
    check_rag_scope,
    create_tool_server,
    prepare_sql_query,
)


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
        return ToolOutput(
            success=True, data={"status": "ready", "rows": [], "evidences": []}
        )


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
        return ToolOutput(
            success=True, data={"status": "ready", "columns": [], "rows": []}
        )


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
        return ToolOutput(
            success=True,
            data={
                "status": "ready",
                "query_id": "q",
                "parameters": {},
                "columns": [],
                "rows": [],
            },
        )


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


def _runtime(db_session, tool_server=None):
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
            tool_server=tool_server,
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
    # T4: tool_runtime_unexpected_error is INFRA, so it is retried once.
    assert [event.event_type for event in events] == ["tool_started", "tool_failed"] * 2
    assert "secret document text" not in str(events)
    records = _records(db_session, attempt)
    assert [record.attempt_no for record in records] == [1, 2]
    for record in records:
        assert record.status == "failed"
        assert record.error_code == "tool_runtime_unexpected_error"
    persisted = repr([vars(event) for event in events] + [vars(r) for r in records])
    assert "private-driver-detail-must-not-persist" not in persisted
    assert "secret document text" not in persisted
    assert "private-driver-detail-must-not-persist" not in repr(result)


@pytest.mark.parametrize(
    ("signal", "code"),
    [
        (ModelCallCancelled, "task_cancelled"),
        (ModelBudgetExceeded, "model_budget_exhausted"),
    ],
)
def test_tool_runtime_records_a_task_stop_signal_and_lets_it_stop_the_task(
    db_session, signal, code
) -> None:
    runtime, attempt, company = _runtime(db_session)

    with pytest.raises(signal):
        runtime.execute(
            _FaultyRagTool(signal("stop")),
            ToolInput(
                parameters={
                    "company_id": company.id,
                    "document_ids": [11],
                    "question": "问题",
                }
            ),
        )

    record = (
        db_session.query(ToolCallRecord)
        .filter(ToolCallRecord.execution_attempt_id == attempt.id)
        .one()
    )
    assert record.status == "failed"
    assert record.error_code == code


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
    assert event.details == {"error_class": "denied"}
    assert db_session.query(ToolCallRecord).one().status == "denied"
    observation = observation_from_runtime_tool_rejection(
        db_session,
        case_id="runtime-document-scope-denial",
        task_id=attempt.task_id,
    )
    assert observation.runtime_tool_denial_status == "passed"
    assert observation.tool_execution_prevented_status == "passed"
    assert observation.actual_tool_denial_codes == ["tool_document_scope_denied"]


def _service(db_session, run=None):
    """An in-process agent-tools server; ran records every search it really ran."""
    ran: list[dict] = []

    def search(arguments):
        ran.append(arguments)
        if run is not None:
            return run(arguments)
        return ToolOutput(
            success=True, data={"status": "ready", "rows": [], "evidences": []}
        )

    server = create_tool_server(
        signing_key=get_settings().tool_context_signing_key.get_secret_value().encode(),
        session_factory=lambda: nullcontext(db_session),
        tools={"rag_search": ServiceTool(run=search, check=check_rag_scope)},
    )
    return server, ran


def _turn_service_on(monkeypatch, **overrides) -> None:
    settings = get_settings().model_copy(
        update={"tool_service_enabled": True, **overrides}
    )
    monkeypatch.setattr(tool_runtime, "runtime_settings", lambda: settings)


def test_tool_runtime_rejects_the_same_illegal_scope_in_process_or_on_the_service(
    db_session, monkeypatch
) -> None:
    server, ran = _service(db_session)
    runtime, _attempt, company = _runtime(db_session, tool_server=server)
    illegal_input = ToolInput(
        parameters={"company_id": company.id, "document_ids": [12], "question": "q"}
    )
    local_reader = _FakeRagTool()

    local_result = runtime.execute(local_reader, illegal_input)
    _turn_service_on(monkeypatch)
    service_result = runtime.execute(_FakeRagTool(), illegal_input)

    assert local_result.error_code == "tool_document_scope_denied"
    assert service_result.error_code == local_result.error_code
    assert local_reader.inputs == []
    assert ran == []


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
    assert event.details == {"error_class": "denied"}


def test_tool_runtime_denies_revoked_user_before_the_service_is_called(
    db_session, monkeypatch
) -> None:
    server, ran = _service(db_session)
    runtime, attempt, company = _runtime(db_session, tool_server=server)
    _turn_service_on(monkeypatch)
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

    result = runtime.execute(
        reader,
        ToolInput(
            parameters={"company_id": company.id, "document_ids": [11], "question": "q"}
        ),
    )

    assert result.error_code == "tool_current_authorization_denied"
    assert reader.inputs == []
    assert ran == []


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
        "schema": "rag_search/v2",
        "error_class": "caller_error",
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


def _search(company) -> ToolInput:
    return ToolInput(
        parameters={"company_id": company.id, "document_ids": [11], "question": "退货"}
    )


def test_service_on_sends_rag_search_there_and_never_runs_it_locally(
    db_session, monkeypatch
) -> None:
    server, ran = _service(db_session)
    runtime, attempt, company = _runtime(db_session, tool_server=server)
    _turn_service_on(monkeypatch)
    local = _FakeRagTool()

    result = runtime.execute(local, _search(company))

    assert result.success, result.error_code
    assert result.evidence == []
    assert local.inputs == []
    # The service's own re-check passed: the signed document scope matched.
    assert ran == [
        {
            "company_id": company.id,
            "document_ids": [11],
            "question": "退货",
            "_runtime_database_timeout_ms": 10_000,
        }
    ]
    record = (
        db_session.query(ToolCallRecord)
        .filter(ToolCallRecord.execution_attempt_id == attempt.id)
        .one()
    )
    assert record.status == "succeeded"


def test_service_and_in_process_return_the_same_result(db_session, monkeypatch) -> None:
    data = {
        "status": "ready",
        "retrieval_policy_id": "paragraph_jieba_rrf_rerank_v1",
        "degraded": False,
        "evidences": [
            {
                "chunk_id": 7,
                "document_id": 11,
                "content": "退货需要主管审批。",
                "score": 0.8125,
                "document_name": "退货制度",
            }
        ],
    }
    tool = _FaultyRagTool(ToolOutput(success=True, data=data))
    # The service runs the very same tool, so only the transport differs.
    server, _ran = _service(
        db_session, run=lambda arguments: tool.execute(ToolInput(parameters=arguments))
    )
    runtime, _attempt, company = _runtime(db_session, tool_server=server)

    in_process = runtime.execute(tool, _search(company))
    _turn_service_on(monkeypatch)
    via_service = runtime.execute(_FakeRagTool(), _search(company))

    assert in_process.success and via_service.success
    assert via_service.data == in_process.data
    assert via_service.evidence == in_process.evidence
    assert [call.parameters for call in tool.inputs] == [tool.inputs[0].parameters] * 2


def test_service_down_fails_clearly_and_never_falls_back(
    db_session, monkeypatch
) -> None:
    runtime, attempt, company = _runtime(
        db_session, tool_server="http://127.0.0.1:9/mcp"
    )
    _turn_service_on(monkeypatch, tool_server_timeout_seconds=2.0)
    local = _FakeRagTool()
    started = monotonic()

    result = runtime.execute(local, _search(company))

    assert result.error_code == "mcp_transport_unavailable"
    assert monotonic() - started < 5
    assert local.inputs == []
    # T4: the outage is retried once on the service; both tries are audited.
    first, second = _records(db_session, attempt)
    assert first.logical_call_id == second.logical_call_id
    for record in (first, second):
        assert record.status == "failed"
        assert record.error_class == "infra_error"


def test_service_off_runs_the_tool_in_process(db_session) -> None:
    # conftest turns the service off for unit tests.
    server, ran = _service(db_session)
    runtime, _attempt, company = _runtime(db_session, tool_server=server)
    local = _FakeRagTool()

    assert runtime.execute(local, _search(company)).success
    assert len(local.inputs) == 1
    assert ran == []


def test_an_in_process_tool_never_goes_to_the_service(db_session, monkeypatch) -> None:
    # Since M3 every runtime tool is "mcp"; a small local tool would be in_process.
    local_sql = [
        replace(d, transport="in_process") if d.name == "sql_query" else d
        for d in catalog.TOOLS
    ]
    registry = ToolRegistry(local_sql)
    monkeypatch.setattr(tool_runtime, "default_registry", lambda: registry)
    runtime, _attempt, _company = _runtime(
        db_session, tool_server="http://127.0.0.1:9/mcp"
    )
    _turn_service_on(monkeypatch)
    sql = _FakeSqlTool()

    result = runtime.execute(sql, ToolInput(parameters={"sql": "SELECT 1"}))

    assert result.success, result.error_code
    assert len(sql.inputs) == 1


def test_a_failure_on_the_service_keeps_its_own_code(db_session, monkeypatch) -> None:
    server, _ran = _service(
        db_session,
        run=lambda arguments: ToolOutput(
            success=False, error_code="rag_search_unavailable"
        ),
    )
    runtime, _attempt, company = _runtime(db_session, tool_server=server)
    _turn_service_on(monkeypatch)

    result = runtime.execute(_FakeRagTool(), _search(company))

    assert result.error_code == "rag_search_unavailable"
    assert result.error == "工具执行暂时不可用。"


def _with_data_source(db_session, attempt, company):
    """Give the task the frozen company data source the service will resolve."""
    task = db_session.get(AnalysisTask, attempt.task_id)
    source = BusinessDataSource(
        company_id=company.id,
        name="runtime-business",
        connection_config={"host": "db", "database": "business", "user": "readonly"},
        credential_env_var="BUSINESS_DATABASE_PASSWORD",
    )
    db_session.add(source)
    db_session.flush()
    snapshot = SchemaSnapshot(
        data_source_id=source.id,
        fingerprint="r" * 64,
        catalog={"tables": {"sales_orders": [{"name": "region"}]}},
        discovered_by_user_id=task.user_id,
    )
    db_session.add(snapshot)
    db_session.flush()
    task.data_source_id, task.schema_snapshot_id = source.id, snapshot.id
    db_session.commit()
    return source, snapshot


def _sql_service(db_session):
    return create_tool_server(
        signing_key=get_settings().tool_context_signing_key.get_secret_value().encode(),
        session_factory=lambda: nullcontext(db_session),
        tools={"sql_query": ServiceTool(prepare=prepare_sql_query)},
    )


# What the driver hands SQLTool: tuples of Decimal and date values.
SQL_ROWS = (
    ["region", "revenue", "day"],
    [("华东", Decimal("12.50"), date(2025, 8, 1)), ("华南", Decimal("0.10"), None)],
)


def test_sql_on_the_service_returns_exactly_what_sql_tool_returns(
    db_session, monkeypatch
) -> None:
    monkeypatch.setattr(
        "app.modules.analysis.data.sql_tool.execute_readonly_sql",
        lambda sql, allowed_tables, **kwargs: SQL_ROWS,
    )
    runtime, attempt, company = _runtime(
        db_session, tool_server=_sql_service(db_session)
    )
    source, snapshot = _with_data_source(db_session, attempt, company)
    query = ToolInput(parameters={"sql": "SELECT region FROM sales_orders"})
    local = SQLTool(
        data_source=source,
        snapshot_catalog=SnapshotCatalog.from_snapshot(snapshot.catalog),
    )

    in_process = runtime.execute(local, query)
    _turn_service_on(monkeypatch)
    via_service = runtime.execute(_FakeSqlTool(), query)

    assert in_process.success and via_service.success, via_service.error_code
    assert via_service.data == in_process.data
    assert via_service.evidence == in_process.evidence
    assert type(via_service.data["rows"][0][1]) is Decimal


def test_a_sql_repair_hint_survives_the_service(db_session, monkeypatch) -> None:
    def refuse(sql, allowed_tables, **kwargs):
        raise ValueError("字段不存在：profit")

    monkeypatch.setattr(
        "app.modules.analysis.data.sql_tool.execute_readonly_sql", refuse
    )
    runtime, attempt, company = _runtime(
        db_session, tool_server=_sql_service(db_session)
    )
    _with_data_source(db_session, attempt, company)
    _turn_service_on(monkeypatch)

    result = runtime.execute(
        _FakeSqlTool(), ToolInput(parameters={"sql": "SELECT profit FROM sales_orders"})
    )

    assert (result.error_code, result.error, result.repairable) == (
        "sql_validation_error",
        "字段不存在：profit",
        True,
    )


class _FlakyRagTool(_FakeRagTool):
    """Fails with the given codes first, then answers like _FakeRagTool."""

    def __init__(self, *codes: str) -> None:
        super().__init__()
        self.codes = list(codes)

    def execute(self, input: ToolInput) -> ToolOutput:
        if self.codes:
            self.inputs.append(input)
            return ToolOutput(success=False, error_code=self.codes.pop(0))
        return super().execute(input)


def _records(db_session, attempt) -> list[ToolCallRecord]:
    return (
        db_session.query(ToolCallRecord)
        .filter(ToolCallRecord.execution_attempt_id == attempt.id)
        .order_by(ToolCallRecord.id)
        .all()
    )


def test_an_outage_retry_writes_two_records_with_one_logical_id(db_session) -> None:
    """T4 acceptance: one injected outage -> 2 records, one logical_call_id."""
    runtime, attempt, company = _runtime(db_session)
    sleeps: list[float] = []
    runtime._sleep = sleeps.append
    tool = _FlakyRagTool("rag_search_unavailable")

    result = runtime.execute(tool, _search(company))

    assert result.success, result.error_code
    assert len(tool.inputs) == 2
    first, second = _records(db_session, attempt)
    assert first.logical_call_id is not None
    assert first.logical_call_id == second.logical_call_id
    assert [first.attempt_no, second.attempt_no] == [1, 2]
    assert [first.status, second.status] == ["failed", "succeeded"]
    assert [first.error_class, second.error_class] == ["infra_error", None]
    assert len(sleeps) == 1
    # The budget stage ran once: a retry is not a second call.
    task = db_session.get(AnalysisTask, attempt.task_id)
    assert task.tool_budget_usage["calls"] == 1


@pytest.mark.parametrize("code", ["rag_input_missing", "tool_circuit_open"])
def test_a_caller_error_or_an_open_circuit_is_not_retried(db_session, code) -> None:
    runtime, attempt, company = _runtime(db_session)
    sleeps: list[float] = []
    runtime._sleep = sleeps.append
    tool = _FlakyRagTool(code)

    assert runtime.execute(tool, _search(company)).error_code == code
    assert len(tool.inputs) == 1
    assert sleeps == []
    (record,) = _records(db_session, attempt)
    assert record.attempt_no == 1


def test_the_service_logs_the_logical_call_id(db_session, monkeypatch, caplog) -> None:
    server, _ran = _service(db_session)
    runtime, attempt, company = _runtime(db_session, tool_server=server)
    _turn_service_on(monkeypatch)
    # Alembic's fileConfig in the test setup disables loggers created before it.
    monkeypatch.setattr(server_module.logger, "disabled", False)

    with caplog.at_level("INFO", logger="app.tool_service.server"):
        assert runtime.execute(_FakeRagTool(), _search(company)).success

    (record,) = _records(db_session, attempt)
    assert f"logical_call_id={record.logical_call_id}" in caplog.text


class _BigSqlTool(_FakeSqlTool):
    def execute(self, input: ToolInput) -> ToolOutput:
        self.inputs.append(input)
        rows = [["华东", 1000 + i] for i in range(5000)]
        return ToolOutput(
            success=True,
            data={"status": "ready", "columns": ["region", "revenue"], "rows": rows},
        )


def test_a_5000_row_sql_result_is_cut_to_its_limit_and_marked(db_session) -> None:
    runtime, attempt, _company = _runtime(db_session)

    result = runtime.execute(_BigSqlTool(), ToolInput(parameters={"sql": "SELECT 1"}))

    assert result.success, result.error_code
    assert result.data["truncated"] is True
    assert 0 < len(result.data["rows"]) < 5000
    (record,) = _records(db_session, attempt)
    assert record.metadata_json["result_truncated"] is True
    assert record.metadata_json["result_tokens"] <= 8_000
    assert record.metadata_json["row_count"] == len(result.data["rows"])


class _HugeRagTool(_FakeRagTool):
    def execute(self, input: ToolInput) -> ToolOutput:
        self.inputs.append(input)
        chunk = {"chunk_id": 1, "document_id": 11, "content": "退货政策。" * 5000}
        return ToolOutput(
            success=True, data={"status": "ready", "rows": [], "evidences": [chunk]}
        )


def test_an_oversized_result_of_a_reject_tool_is_refused_once(db_session) -> None:
    runtime, attempt, company = _runtime(db_session)
    sleeps: list[float] = []
    runtime._sleep = sleeps.append
    tool = _HugeRagTool()

    result = runtime.execute(tool, _search(company))

    assert result.error_code == "tool_result_too_large"
    assert result.model_feedback and "8000" in result.model_feedback
    assert len(tool.inputs) == 1 and sleeps == []
    (record,) = _records(db_session, attempt)
    assert record.error_class == "caller_error"
    assert record.metadata_json["result_tokens"] > 8_000


def test_a_small_result_records_its_size(db_session) -> None:
    runtime, attempt, company = _runtime(db_session)

    assert runtime.execute(_FakeRagTool(), _search(company)).success

    (record,) = _records(db_session, attempt)
    assert record.metadata_json["result_truncated"] is False
    assert 0 < record.metadata_json["result_tokens"] < 100


def test_a_tool_far_past_its_timeout_keeps_its_answer_and_warns(
    db_session, monkeypatch
) -> None:
    runtime, attempt, company = _runtime(db_session)
    monkeypatch.setattr(ToolRuntime, "_timeout_ms", staticmethod(lambda tool: 1))

    class _Slow(_FakeRagTool):
        def execute(self, input: ToolInput) -> ToolOutput:
            sleep(0.01)
            return super().execute(input)

    assert runtime.execute(_Slow(), _search(company)).success
    (event,) = (
        db_session.query(WorkflowEvent)
        .filter(
            WorkflowEvent.execution_attempt_id == attempt.id,
            WorkflowEvent.event_type == "tool_timeout_overrun",
        )
        .all()
    )
    assert event.details["timeout_ms"] == 1
    assert event.details["duration_ms"] >= 10


def test_the_worker_waits_for_each_tool_as_long_as_it_declares(
    db_session, monkeypatch
) -> None:
    runtime, _attempt, _company = _runtime(db_session, tool_server="unused")
    _turn_service_on(monkeypatch)
    waits: list[float] = []

    def fake_call_service(*args, timeout_seconds, **kwargs):
        waits.append(timeout_seconds)
        return ToolOutput(
            success=True, data={"status": "ready", "columns": [], "rows": []}
        )

    monkeypatch.setattr(tool_runtime, "call_service", fake_call_service)

    assert runtime.execute(
        _FakeSqlTool(), ToolInput(parameters={"sql": "SELECT 1"})
    ).success
    # Longer than the frozen 10 s statement timeout, so that code comes back itself.
    assert waits == [12.0]
