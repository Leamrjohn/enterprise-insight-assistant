import time
from contextlib import nullcontext
from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest
from app.db.session import set_tenant_scope
from app.modules.analysis.tool_protocol import ToolOutput
from app.modules.documents.models import Documents
from app.modules.identity.models import User
from app.modules.input_artifacts.models import InputArtifact, InputArtifactVersion
from app.modules.memory.models import AnalysisMemory, MemorySource
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
from app.modules.workflow.models import (
    AnalysisTask,
    AnalysisTaskDocument,
    AnalysisTaskInputArtifactVersion,
)
from app.tool_service import documents as document_tools
from app.tool_service import history, lookups
from app.tool_service.server import (
    DEFAULT_TOOLS,
    ServiceTool,
    check_rag_scope,
    create_tool_server,
    on_task_data,
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
            logical_call_id="call-1",
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


# --- T11a: lookups run on the task's own source, like sql_query ----------------


@pytest.fixture
def lookup_server(db_session, data_context):
    snapshot = data_context["own"][1]
    snapshot.catalog = {
        "tables": {
            "sales_orders": [
                {"name": name}
                for name in ("id", "total_amount", "order_date", "status")
            ]
        }
    }
    db_session.flush()
    return create_tool_server(
        signing_key=KEY,
        session_factory=lambda: nullcontext(db_session),
        clock=lambda: NOW,
        tools={
            name: ServiceTool(prepare=on_task_data(build))
            for name, build in (
                ("dimension_list", lookups.dimension_list),
                ("data_freshness", lookups.data_freshness),
            )
        },
    )


def test_every_lookup_is_served_from_the_tasks_data():
    for name in ("metric_lookup", "dimension_list", "data_freshness"):
        tool = DEFAULT_TOOLS[name]
        assert isinstance(tool, ServiceTool) and tool.prepare is not None


def test_a_lookup_queries_only_the_tasks_own_data_source(
    monkeypatch, lookup_server, seeded, data_context
):
    runs = []

    def execute(sql, allowed_tables, **kwargs):
        runs.append(kwargs["data_source"].id)
        return ["earliest", "latest"], [(date(2024, 1, 1), date(2025, 9, 30))]

    monkeypatch.setattr(
        "app.modules.analysis.data.sql_tool.execute_readonly_sql", execute
    )

    result = _query(lookup_server, seeded, {"metric": "销售额"}, name="data_freshness")

    assert result.success, result.error_code
    assert runs == [data_context["own"][0].id]
    # Dates cross the service boundary as dates, not as text.
    assert result.data["metrics"][0]["latest"] == date(2025, 9, 30)


def test_a_task_without_a_data_source_never_runs_a_lookup(
    db_session, lookup_server, seeded, sql_runs
):
    seeded["task"].data_source_id = None
    db_session.flush()

    result = _query(
        lookup_server, seeded, {"field": "sales_orders.status"}, name="dimension_list"
    )

    assert result.error_code == "data_source_not_allowed"
    assert sql_runs == []


# --- T11a: doc_list and doc_read read only what the task froze and the user sees --


def _freeze(db_session, seeded, *document_ids):
    db_session.add_all(
        AnalysisTaskDocument(task_id=seeded["task"].id, document_id=document_id)
        for document_id in document_ids
    )
    db_session.flush()


def _readable(db_session, seeded, **overrides):
    return document_tools.readable_document_ids(
        db_session, _context(seeded, **overrides)
    )


def test_readable_documents_are_the_frozen_ones_the_user_may_see(
    db_session, seeded, documents
):
    _freeze(db_session, seeded, documents["visible"], documents["admin_only"])

    assert _readable(db_session, seeded) == {documents["visible"]}


def test_a_visible_document_the_task_did_not_freeze_is_not_readable(
    db_session, seeded, documents
):
    _freeze(db_session, seeded, documents["admin_only"])

    assert _readable(db_session, seeded) == set()


def test_another_companys_document_is_never_readable_even_if_frozen(
    db_session, seeded, documents
):
    _freeze(db_session, seeded, documents["visible"], documents["other_company"])

    assert _readable(db_session, seeded) == {documents["visible"]}


def test_readability_follows_the_role_in_the_database_now(
    db_session, seeded, documents
):
    _freeze(db_session, seeded, documents["visible"], documents["admin_only"])
    seeded["member"].role = "admin"
    db_session.flush()
    assert _readable(db_session, seeded) == {
        documents["visible"],
        documents["admin_only"],
    }

    seeded["member"].role = "analyst"  # lowered after the worker signed as admin
    db_session.flush()
    assert _readable(db_session, seeded, authorized_role="admin") == {
        documents["visible"]
    }


@pytest.fixture
def doc_server(db_session, seeded, documents):
    for key, text in (("visible", "退货需要主管审批。" * 500), ("admin_only", "机密")):
        db_session.get(Documents, documents[key]).content = text
    _freeze(db_session, seeded, documents["visible"], documents["admin_only"])
    return create_tool_server(
        signing_key=KEY,
        session_factory=lambda: nullcontext(db_session),
        clock=lambda: NOW,
        tools={name: DEFAULT_TOOLS[name] for name in ("doc_list", "doc_read")},
    )


def test_doc_list_shows_only_the_readable_documents(doc_server, seeded, documents):
    result = _query(doc_server, seeded, {}, name="doc_list")

    assert result.success, result.error_code
    assert [d["document_id"] for d in result.data["documents"]] == [
        documents["visible"]
    ]
    assert result.data["documents"][0]["name"] == "制度.txt"


def test_doc_read_returns_one_part_and_where_the_next_one_starts(
    doc_server, seeded, documents
):
    first = _query(
        doc_server, seeded, {"document_id": documents["visible"]}, name="doc_read"
    )
    last = _query(
        doc_server,
        seeded,
        {"document_id": documents["visible"], "offset": 4000},
        name="doc_read",
    )

    assert len(first.data["content"]) == document_tools.PART_CHARS
    assert first.data["next_offset"] == 4000
    assert len(last.data["content"]) == 500  # 4500 characters in all
    assert last.data["next_offset"] is None


@pytest.mark.parametrize("which", ["admin_only", "other_company", "missing"])
def test_an_unreadable_document_looks_the_same_as_a_missing_one(
    doc_server, seeded, documents, which
):
    document_id = documents.get(which, 999_999)

    result = _query(doc_server, seeded, {"document_id": document_id}, name="doc_read")

    assert (result.error_code, result.error, result.repairable) == (
        "tool_arguments_invalid",
        "没有这份可读文档。",
        True,
    )
    assert (
        result.model_feedback == f"没有这份可读文档。可读编号：{documents['visible']}"
    )


# --- T11b: doc_version_diff compares two readable versions of one document -------


@pytest.fixture
def versions(db_session, seeded, documents):
    old = db_session.get(Documents, documents["visible"])
    old.version_group, old.version_number = "退货制度", 1
    old.content = "第一条 退货需主管审批。\n第二条 七日内办理。"
    new = Documents(
        uploaded_by_user_id=seeded["user"].id,
        company_id=seeded["company"].id,
        name="制度.txt",
        source="test",
        min_view_role="any",
        version_group="退货制度",
        version_number=2,
        content="第一条 退货需主管审批。\n第二条 十五日内办理。",
    )
    db_session.add(new)
    db_session.flush()
    _freeze(db_session, seeded, old.id, new.id, documents["admin_only"])
    return {"old": old.id, "new": new.id, "admin_only": documents["admin_only"]}


@pytest.fixture
def diff(db_session, seeded):
    server = create_tool_server(
        signing_key=KEY,
        session_factory=lambda: nullcontext(db_session),
        clock=lambda: NOW,
        tools={"doc_version_diff": DEFAULT_TOOLS["doc_version_diff"]},
    )
    return lambda old, new: _query(
        server,
        seeded,
        {"document_id": old, "other_document_id": new},
        name="doc_version_diff",
    )


def test_doc_version_diff_shows_what_changed_between_versions(diff, versions):
    result = diff(versions["old"], versions["new"])

    assert result.success, result.error_code
    assert "-第二条 七日内办理。" in result.data["diff"]
    assert "+第二条 十五日内办理。" in result.data["diff"]
    assert result.data["truncated"] is False


def test_doc_version_diff_refuses_documents_of_different_groups(
    db_session, diff, versions
):
    db_session.get(Documents, versions["new"]).version_group = "报销制度"
    db_session.flush()

    result = diff(versions["old"], versions["new"])

    assert (result.error_code, result.repairable) == ("tool_arguments_invalid", True)
    assert result.error == "这两份文档不是同一份文档的不同版本。"


def test_doc_version_diff_never_compares_an_unreadable_document(diff, versions):
    result = diff(versions["old"], versions["admin_only"])

    assert result.error == "没有这份可读文档。"


# --- T11b: memory_search finds only the caller's own conclusions -----------------


def _memory(db_session, *, company, user, statement):
    task = AnalysisTask(
        user_id=user.id,
        company_id=company.id,
        question="以前的问题",
        status="completed",
        stage="completed",
    )
    db_session.add(task)
    db_session.flush()
    source = MemorySource(
        company_id=company.id,
        source_task_id=task.id,
        source_type="validated_report",
        idempotency_key=f"tool-server-memory:{task.id}",
    )
    db_session.add(source)
    db_session.flush()
    memory = AnalysisMemory(
        company_id=company.id,
        user_id=user.id,
        source_task_id=task.id,
        memory_source_id=source.id,
        memory_type="validated_report_facts",
        content={"confirmed_facts": [{"statement": statement}]},
    )
    db_session.add(memory)
    db_session.flush()
    return memory


@pytest.fixture
def colleague(db_session, seeded):
    user = User(name="tool-server-colleague", api_key="tool-server-colleague-key")
    db_session.add(user)
    db_session.flush()
    db_session.add(
        CompanyMember(company_id=seeded["company"].id, user_id=user.id, role="admin")
    )
    db_session.flush()
    return user


def test_memory_search_finds_only_the_callers_own_conclusions(
    db_session, seeded, colleague
):
    mine = _memory(
        db_session,
        company=seeded["company"],
        user=seeded["user"],
        statement="华东销售额八月下降",
    )
    _memory(
        db_session,
        company=seeded["company"],
        user=colleague,
        statement="华东销售额八月上升",
    )
    server = create_tool_server(
        signing_key=KEY,
        session_factory=lambda: nullcontext(db_session),
        clock=lambda: NOW,
        tools={"memory_search": DEFAULT_TOOLS["memory_search"]},
    )

    result = _query(server, seeded, {"query": "华东销售额"}, name="memory_search")

    assert result.success, result.error_code
    assert [m["memory_id"] for m in result.data["memories"]] == [mine.id]
    assert db_session.get(AnalysisMemory, mine.id).use_count == 0


# --- T11b: report_export reads a finished report only if all it drew on is readable


def _report_task(
    db_session,
    seeded,
    *,
    user,
    cited,
    status="completed",
    question="八月华东销售额为何下降",
    summary="华东销售额下降 12%。",
):
    task = AnalysisTask(
        user_id=user.id,
        company_id=seeded["company"].id,
        question=question,
        status=status,
        stage="completed",
        result_data={
            "report": {
                "executive_summary": summary,
                "confirmed_facts": [{"statement": "八月华东销售额 120 万元。"}],
                "recommendations": [{"action": "复核华东大客户订单。"}],
                "document_citations": [
                    {
                        "chunk_id": index + 1,
                        "document_id": document_id,
                        "excerpt": "摘录",
                    }
                    for index, document_id in enumerate(cited)
                ],
            }
        },
    )
    db_session.add(task)
    db_session.flush()
    return task


def _readable_report(db_session, seeded, task, **overrides):
    return history.report_readable(db_session, _context(seeded, **overrides), task)


def test_a_colleagues_report_on_visible_documents_is_readable(
    db_session, seeded, documents, colleague
):
    task = _report_task(
        db_session, seeded, user=colleague, cited=[documents["visible"]]
    )

    assert _readable_report(db_session, seeded, task) is True


def test_a_report_citing_a_document_above_the_callers_role_is_not_readable(
    db_session, seeded, documents, colleague
):
    task = _report_task(
        db_session,
        seeded,
        user=colleague,
        cited=[documents["visible"], documents["admin_only"]],
    )
    assert _readable_report(db_session, seeded, task) is False

    seeded["member"].role = "admin"  # the same check, with the role as it is now
    db_session.flush()
    assert _readable_report(db_session, seeded, task) is True


def test_a_report_citing_another_companys_document_is_not_readable(
    db_session, seeded, documents, colleague
):
    task = _report_task(
        db_session, seeded, user=colleague, cited=[documents["other_company"]]
    )

    assert _readable_report(db_session, seeded, task) is False


def test_a_citation_that_names_no_document_denies(db_session, seeded, colleague):
    task = _report_task(db_session, seeded, user=colleague, cited=[None])

    assert _readable_report(db_session, seeded, task) is False


@pytest.mark.parametrize("status", ["running", "awaiting_review", "failed"])
def test_an_unfinished_report_is_not_readable(
    db_session, seeded, documents, colleague, status
):
    task = _report_task(
        db_session, seeded, user=colleague, cited=[documents["visible"]], status=status
    )

    assert _readable_report(db_session, seeded, task) is False


def test_another_companys_report_is_never_readable(
    db_session, seeded, documents, colleague
):
    task = _report_task(
        db_session, seeded, user=colleague, cited=[documents["visible"]]
    )

    assert (
        _readable_report(db_session, seeded, task, company_id=seeded["other"].id)
        is False
    )


def test_a_report_that_used_an_attachment_is_readable_only_by_its_author(
    db_session, seeded, documents, colleague
):
    task = _report_task(
        db_session, seeded, user=colleague, cited=[documents["visible"]]
    )
    upload = InputArtifact(
        company_id=seeded["company"].id,
        uploaded_by_user_id=colleague.id,
        kind="attachment",
    )
    db_session.add(upload)
    db_session.flush()
    version = InputArtifactVersion(
        artifact_id=upload.id,
        version_number=1,
        original_filename="附件.txt",
        raw_object_key=f"quarantine/{seeded['company'].id}/t11b",
        byte_size=12,
        sha256="b" * 64,
        status="ready",
    )
    db_session.add(version)
    db_session.flush()
    db_session.add(
        AnalysisTaskInputArtifactVersion(
            task_id=task.id, artifact_version_id=version.id, position=0
        )
    )
    db_session.flush()

    assert _readable_report(db_session, seeded, task) is False
    assert _readable_report(db_session, seeded, task, actor_id=colleague.id) is True


def test_report_export_returns_the_text_or_one_answer_for_every_refusal(
    db_session, seeded, documents, colleague
):
    readable = _report_task(
        db_session, seeded, user=colleague, cited=[documents["visible"]]
    )
    forbidden = _report_task(
        db_session, seeded, user=colleague, cited=[documents["admin_only"]]
    )
    server = create_tool_server(
        signing_key=KEY,
        session_factory=lambda: nullcontext(db_session),
        clock=lambda: NOW,
        tools={"report_export": DEFAULT_TOOLS["report_export"]},
    )

    result = _query(server, seeded, {"task_id": readable.id}, name="report_export")
    refusals = [
        _query(server, seeded, {"task_id": task_id}, name="report_export")
        for task_id in (forbidden.id, 999_999)
    ]

    assert result.success, result.error_code
    assert "华东销售额下降 12%" in result.data["text"]
    assert "- 复核华东大客户订单。" in result.data["text"]
    assert {(r.error_code, r.error) for r in refusals} == {
        ("tool_arguments_invalid", "没有这份可读报告。")
    }


def test_report_search_finds_readable_reports_by_their_words(
    db_session, seeded, documents, colleague
):
    readable = _report_task(
        db_session, seeded, user=colleague, cited=[documents["visible"]]
    )
    _report_task(  # same words, but cites a document above the caller's role
        db_session, seeded, user=colleague, cited=[documents["admin_only"]]
    )
    _report_task(  # readable, but about something else
        db_session,
        seeded,
        user=colleague,
        cited=[documents["visible"]],
        question="西部应收账款风险",
        summary="西部应收逾期增加。",
    )
    server = create_tool_server(
        signing_key=KEY,
        session_factory=lambda: nullcontext(db_session),
        clock=lambda: NOW,
        tools={"report_search": DEFAULT_TOOLS["report_search"]},
    )

    result = _query(server, seeded, {"query": "华东销售额"}, name="report_search")

    assert result.success, result.error_code
    assert result.data["reports"] == [
        {
            "task_id": readable.id,
            "question": "八月华东销售额为何下降",
            "completed_at": None,
            "summary": "华东销售额下降 12%",
        }
    ]
