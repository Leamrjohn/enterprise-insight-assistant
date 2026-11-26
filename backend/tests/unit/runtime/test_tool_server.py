import time
from contextlib import nullcontext
from dataclasses import replace
from decimal import Decimal

import pytest
from app.db.session import set_tenant_scope
from app.modules.analysis.tool_protocol import ToolOutput
from app.modules.documents.models import Documents
from app.modules.identity.models import User
from app.modules.organizations.models import (
    BusinessDataSource,
    Company,
    CompanyMember,
    SchemaSnapshot,
)
from app.modules.runtime.tools.context import (
    RuntimeContext,
    document_scope_sha256,
    issue,
)
from app.modules.runtime.tools.mcp_client import call_tool
from app.modules.workflow.models import AnalysisTask
from app.tool_service.server import (
    ServiceTool,
    check_rag_scope,
    create_tool_server,
    prepare_sql_query,
    prepare_template_query,
)

KEY = b"worker-and-tool-service-share-this"
NOW = 1_800_000_000


@pytest.fixture
def seeded(db_session):
    user = User(name="tool-server-user", api_key="tool-server-key")
    company = Company(name="tool-server-company")
    other = Company(name="tool-server-other")
    db_session.add_all([user, company, other])
    db_session.flush()
    member = CompanyMember(company_id=company.id, user_id=user.id, role="analyst")
    task = AnalysisTask(
        user_id=user.id,
        company_id=company.id,
        question="回声",
        status="running",
        stage="querying_data",
        active_execution_id="exec-1",
    )
    db_session.add_all([member, task])
    db_session.flush()
    return {
        "user": user,
        "company": company,
        "other": other,
        "task": task,
        "member": member,
    }


@pytest.fixture
def executed():
    return []


@pytest.fixture
def server(db_session, executed):
    def echo(arguments):
        executed.append(arguments)
        return {"echo": arguments["text"]}

    return create_tool_server(
        signing_key=KEY,
        session_factory=lambda: nullcontext(db_session),
        clock=lambda: NOW,
        tools={"echo": echo},
    )


def _context(seeded, **overrides) -> RuntimeContext:
    return replace(
        issue(
            task_id=seeded["task"].id,
            execution_id="exec-1",
            actor_id=seeded["user"].id,
            authorized_role="analyst",
            company_id=seeded["company"].id,
            document_scope_sha256="a" * 64,
            now=NOW,
            ttl_seconds=60,
        ),
        **overrides,
    )


def _call(server, context, *, key=KEY):
    return call_tool(
        server, "echo", {"text": "你好"}, context, key=key, timeout_seconds=5
    )


def test_signed_call_from_a_current_member_runs(server, seeded, executed):
    result = _call(server, _context(seeded))

    assert result.success
    assert result.data == {"echo": "你好"}
    assert executed == [{"text": "你好"}]


def test_forged_signature_never_runs(server, seeded, executed):
    result = _call(server, _context(seeded), key=b"guessed-key")

    assert result.error_code == "tool_context_signature_invalid"
    assert executed == []


def test_expired_context_never_runs(server, seeded, executed):
    result = _call(server, _context(seeded, expires_at=NOW))

    assert result.error_code == "tool_context_expired"
    assert executed == []


def test_other_company_never_runs(server, seeded, executed):
    # Validly signed, but the user is not a member there and the task is not theirs.
    result = _call(server, _context(seeded, company_id=seeded["other"].id))

    assert result.error_code == "tool_current_authorization_denied"
    assert executed == []


def test_removed_member_never_runs_even_with_a_valid_signature(
    db_session, server, seeded, executed
):
    seeded["member"].status = "removed"
    db_session.flush()

    result = _call(server, _context(seeded))

    assert result.error_code == "tool_current_authorization_denied"
    assert executed == []


def test_taken_over_execution_never_runs(db_session, server, seeded, executed):
    seeded["task"].active_execution_id = "exec-2"
    db_session.flush()

    result = _call(server, _context(seeded))

    assert result.error_code == "tool_current_authorization_denied"
    assert executed == []


def test_unreachable_service_fails_clearly_within_the_timeout(seeded):
    started = time.monotonic()

    result = call_tool(
        "http://127.0.0.1:9/mcp",
        "echo",
        {"text": "你好"},
        _context(seeded),
        key=KEY,
        timeout_seconds=2,
    )

    assert result.error_code == "mcp_transport_unavailable"
    assert time.monotonic() - started < 3


@pytest.fixture
def documents(db_session, seeded):
    company, other, user = seeded["company"], seeded["other"], seeded["user"]
    rows = [
        Documents(
            uploaded_by_user_id=user.id,
            company_id=company.id,
            name="制度.txt",
            source="test",
            min_view_role="any",
        ),
        Documents(
            uploaded_by_user_id=user.id,
            company_id=company.id,
            name="董事会纪要.txt",
            source="test",
            min_view_role="admin",  # an analyst may not read it
        ),
        Documents(
            uploaded_by_user_id=user.id,
            company_id=other.id,
            name="别家制度.txt",
            source="test",
            min_view_role="any",
        ),
    ]
    # Documents have row-level security: insert each under its own company scope.
    set_tenant_scope(db_session, other.id)
    db_session.add(rows[2])
    db_session.flush()
    set_tenant_scope(db_session, company.id)
    db_session.add_all(rows[:2])
    db_session.flush()
    return {
        "visible": rows[0].id,
        "admin_only": rows[1].id,
        "other_company": rows[2].id,
    }


@pytest.fixture
def rag_server(db_session, executed):
    def search(arguments):
        executed.append(arguments)
        return ToolOutput(
            success=True, data={"status": "ready", "evidences": [], "rows": []}
        )

    return create_tool_server(
        signing_key=KEY,
        session_factory=lambda: nullcontext(db_session),
        clock=lambda: NOW,
        tools={"rag_search": ServiceTool(run=search, check=check_rag_scope)},
    )


def _search(server, seeded, document_ids, *, company_id=None, signed_ids=None, key=KEY):
    company_id = company_id or seeded["company"].id
    context = _context(
        seeded,
        document_scope_sha256=document_scope_sha256(
            seeded["company"].id, signed_ids if signed_ids is not None else document_ids
        ),
    )
    return call_tool(
        server,
        "rag_search",
        {
            "question": "退货流程",
            "company_id": company_id,
            "document_ids": document_ids,
        },
        context,
        key=key,
        timeout_seconds=5,
    )


def test_signed_search_over_visible_documents_runs(
    rag_server, seeded, documents, executed
):
    result = _search(rag_server, seeded, [documents["visible"]])

    assert result.success
    assert result.data["status"] == "ready"
    assert executed[0]["document_ids"] == [documents["visible"]]


def test_search_naming_another_company_never_runs(
    rag_server, seeded, documents, executed
):
    result = _search(
        rag_server, seeded, [documents["visible"]], company_id=seeded["other"].id
    )

    assert result.error_code == "tool_company_scope_denied"
    assert executed == []


def test_documents_other_than_the_signed_ones_never_run(
    rag_server, seeded, documents, executed
):
    # Signed for one document, sent with another added.
    result = _search(
        rag_server,
        seeded,
        [documents["visible"], documents["admin_only"]],
        signed_ids=[documents["visible"]],
    )

    assert result.error_code == "tool_document_scope_denied"
    assert executed == []


@pytest.mark.parametrize("which", ["admin_only", "other_company"])
def test_documents_the_user_cannot_see_never_run(
    rag_server, seeded, documents, executed, which
):
    result = _search(rag_server, seeded, [documents["visible"], documents[which]])

    assert result.error_code == "tool_document_current_authorization_denied"
    assert executed == []


def test_forged_search_never_reaches_the_documents(
    rag_server, seeded, documents, executed
):
    result = _search(rag_server, seeded, [documents["visible"]], key=b"guessed-key")

    assert result.error_code == "tool_context_signature_invalid"
    assert executed == []


def test_a_tool_failure_comes_back_with_its_own_code(db_session, seeded, documents):
    server = create_tool_server(
        signing_key=KEY,
        session_factory=lambda: nullcontext(db_session),
        clock=lambda: NOW,
        tools={
            "rag_search": ServiceTool(
                run=lambda arguments: ToolOutput(
                    success=False, error_code="rag_search_unavailable"
                ),
                check=check_rag_scope,
            )
        },
    )

    result = _search(server, seeded, [documents["visible"]])

    assert result.error_code == "rag_search_unavailable"


CATALOG = {"tables": {"sales_orders": [{"name": "region"}, {"name": "revenue"}]}}


@pytest.fixture
def data_context(db_session, seeded):
    """The task's own data source and schema snapshot, plus another company's."""
    sources = {}
    for key, company in (("own", seeded["company"]), ("other", seeded["other"])):
        set_tenant_scope(db_session, company.id)
        source = BusinessDataSource(
            company_id=company.id,
            name=f"business-{key}",
            connection_config={"host": "db", "database": key, "user": "readonly"},
            credential_env_var="BUSINESS_DATABASE_PASSWORD",
        )
        db_session.add(source)
        db_session.flush()
        snapshot = SchemaSnapshot(
            data_source_id=source.id,
            fingerprint=key[0] * 64,
            catalog=CATALOG,
            discovered_by_user_id=seeded["user"].id,
        )
        db_session.add(snapshot)
        db_session.flush()
        sources[key] = (source, snapshot)
    set_tenant_scope(db_session, seeded["company"].id)
    task = seeded["task"]
    task.data_source_id, task.schema_snapshot_id = (
        sources["own"][0].id,
        sources["own"][1].id,
    )
    db_session.flush()
    return sources


@pytest.fixture
def sql_runs(monkeypatch):
    """Every statement that reached the executor, with the source it ran on."""
    runs = []

    def execute(sql, allowed_tables, **kwargs):
        runs.append({"sql": sql, "data_source": kwargs["data_source"]})
        return ["region", "revenue"], [("华东", Decimal("12.50"))]

    monkeypatch.setattr(
        "app.modules.analysis.data.sql_tool.execute_readonly_sql", execute
    )
    return runs


@pytest.fixture
def sql_server(db_session):
    return create_tool_server(
        signing_key=KEY,
        session_factory=lambda: nullcontext(db_session),
        clock=lambda: NOW,
        tools={
            "sql_query": ServiceTool(prepare=prepare_sql_query),
            "template_query": ServiceTool(prepare=prepare_template_query),
        },
    )


def _query(server, seeded, arguments, *, name="sql_query"):
    return call_tool(
        server, name, arguments, _context(seeded), key=KEY, timeout_seconds=5
    )


def test_sql_runs_on_the_tasks_own_data_source(
    sql_server, seeded, data_context, sql_runs
):
    result = _query(sql_server, seeded, {"sql": "SELECT region FROM sales_orders"})

    assert result.success, result.error_code
    assert [run["data_source"].id for run in sql_runs] == [data_context["own"][0].id]


def test_arguments_cannot_choose_another_data_source(
    sql_server, seeded, data_context, sql_runs
):
    other_source = data_context["other"][0]

    _query(
        sql_server,
        seeded,
        {"sql": "SELECT region FROM sales_orders", "data_source_id": other_source.id},
    )

    assert [run["data_source"].id for run in sql_runs] == [data_context["own"][0].id]


def test_a_task_without_a_data_source_never_runs_sql(
    db_session, sql_server, seeded, sql_runs
):
    result = _query(sql_server, seeded, {"sql": "SELECT region FROM sales_orders"})

    assert result.error_code == "data_source_not_allowed"
    assert sql_runs == []


def test_a_snapshot_of_another_source_never_runs_sql(
    db_session, sql_server, seeded, data_context, sql_runs
):
    seeded["task"].schema_snapshot_id = data_context["other"][1].id
    db_session.flush()

    result = _query(sql_server, seeded, {"sql": "SELECT region FROM sales_orders"})

    assert result.error_code == "data_source_not_allowed"
    assert sql_runs == []


def test_the_service_validates_sql_before_connecting(sql_server, seeded, data_context):
    # The real executor: validation fails before any connection is attempted.
    result = _query(sql_server, seeded, {"sql": "DELETE FROM sales_orders"})

    assert result.error_code == "sql_validation_error"
    assert result.repairable is True
    assert result.error


def test_a_sql_failure_brings_back_what_a_repair_needs(
    monkeypatch, sql_server, seeded, data_context
):
    def refuse(sql, allowed_tables, **kwargs):
        raise ValueError("字段不存在：profit")

    monkeypatch.setattr(
        "app.modules.analysis.data.sql_tool.execute_readonly_sql", refuse
    )

    result = _query(sql_server, seeded, {"sql": "SELECT profit FROM sales_orders"})

    assert (result.error_code, result.error, result.repairable) == (
        "sql_validation_error",
        "字段不存在：profit",
        True,
    )


def test_template_query_runs_on_the_tasks_own_data_source(
    monkeypatch, sql_server, seeded, data_context
):
    runs = []

    def execute(sql, parameters, *, data_source, **kwargs):
        runs.append(data_source)
        return ["region_code"], [("EAST",)]

    monkeypatch.setattr(
        "app.modules.analysis.data.template_query.execute_registered_readonly_query",
        execute,
    )

    result = _query(
        sql_server,
        seeded,
        {
            "query_id": "regional_revenue_comparison",
            "current_month": "2025-08-01",
            "comparison_month": "2025-07-01",
        },
        name="template_query",
    )

    assert result.success, result.error_code
    assert [source.id for source in runs] == [data_context["own"][0].id]
