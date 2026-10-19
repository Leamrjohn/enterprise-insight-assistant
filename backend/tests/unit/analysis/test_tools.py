"""测试 Tool 协议和两个工具实现"""

from app.modules.analysis.catalog.semantic_catalog import BUSINESS_TABLES
from app.modules.analysis.catalog.snapshot_catalog import SnapshotCatalog
from app.modules.analysis.data.sql_tool import SQLTool
from app.modules.analysis.tool_protocol import ToolInput
from app.modules.knowledge.rag.engine import EvidenceRef
from app.modules.knowledge.rag.policy import RetrievalPolicy
from app.modules.knowledge.tool import RAGTool
from app.modules.organizations.models import BusinessDataSource
from psycopg.errors import GroupingError, QueryCanceled


def test_rag_tool_name_and_description():
    tool = RAGTool()
    assert tool.name == "rag_search"
    assert isinstance(tool.description, str)
    assert len(tool.description) > 0


def test_rag_tool_missing_parameters():
    tool = RAGTool()
    result = tool.execute(ToolInput(parameters={"question": "test"}))
    assert result.success is False
    assert result.error is not None


def test_rag_tool_returns_failure_when_embedding_initialization_fails(monkeypatch):
    class FailingEmbeddingProvider:
        def __init__(self) -> None:
            raise RuntimeError("embedding model unavailable")

    def fail_if_database_session_is_created():
        raise AssertionError("database session must not be created")

    monkeypatch.setattr(
        "app.modules.knowledge.tool.LocalEmbeddingProvider",
        FailingEmbeddingProvider,
    )
    monkeypatch.setattr(
        "app.modules.knowledge.tool.SessionLocal",
        fail_if_database_session_is_created,
    )

    result = RAGTool().execute(
        ToolInput(parameters={"question": "test", "company_id": 1})
    )

    assert result.success is False
    assert result.error == "RAG retrieval failed"


class FakeReranker:
    def __init__(self, scores: list[float]) -> None:
        self.scores = scores

    def score(self, question: str, passages: list[str]) -> list[float]:
        return self.scores


def test_rag_tool_uses_reranked_evidence_for_prompt(monkeypatch):
    class FakeSession:
        def execute(self, *_args, **_kwargs) -> None:
            pass

        def close(self) -> None:
            pass

    monkeypatch.setattr("app.modules.knowledge.tool.SessionLocal", FakeSession)
    monkeypatch.setattr("app.modules.knowledge.tool.set_tenant_scope", lambda *_: None)
    monkeypatch.setattr(
        "app.modules.knowledge.tool.LocalEmbeddingProvider", lambda: object()
    )
    monkeypatch.setattr(
        "app.modules.knowledge.tool.retrieve_evidence",
        lambda **kwargs: [
            EvidenceRef(
                chunk_id=1,
                document_id=1,
                content="向量分数高但与合同无关的资料",
                score=0.95,
            ),
            EvidenceRef(
                chunk_id=2,
                document_id=1,
                content="客户合同到期后暂停采购。",
                score=0.61,
            ),
        ],
    )

    result = RAGTool(reranker=FakeReranker([0.12, 0.91])).execute(
        ToolInput(parameters={"question": "客户合同为何影响销售", "company_id": 1})
    )

    assert result.success is True
    assert result.data["status"] == "ready"
    assert [evidence["chunk_id"] for evidence in result.data["evidences"]] == [2, 1]
    assert result.data["evidences"][0]["rerank_score"] == 0.91


def test_rag_tool_rejects_high_vector_score_with_low_rerank_score(monkeypatch):
    class FakeSession:
        def execute(self, *_args, **_kwargs) -> None:
            pass

        def close(self) -> None:
            pass

    monkeypatch.setattr("app.modules.knowledge.tool.SessionLocal", FakeSession)
    monkeypatch.setattr("app.modules.knowledge.tool.set_tenant_scope", lambda *_: None)
    monkeypatch.setattr(
        "app.modules.knowledge.tool.LocalEmbeddingProvider", lambda: object()
    )
    monkeypatch.setattr(
        "app.modules.knowledge.tool.retrieve_evidence",
        lambda **kwargs: [
            EvidenceRef(
                chunk_id=1,
                document_id=1,
                content="无关资料",
                score=0.99,
            )
        ],
    )

    result = RAGTool(reranker=FakeReranker([0.12])).execute(
        ToolInput(parameters={"question": "客户合同为何影响销售", "company_id": 1})
    )

    assert result.success is True
    assert result.data["status"] == "insufficient_evidence"


def test_rag_tool_can_disable_reranking_only_through_server_policy(monkeypatch):
    class FakeSession:
        def execute(self, *_args, **_kwargs) -> None:
            pass

        def close(self) -> None:
            pass

    class FailingReranker:
        def score(self, _question: str, _passages: list[str]) -> list[float]:
            raise AssertionError("disabled reranker must not be called")

    monkeypatch.setattr("app.modules.knowledge.tool.SessionLocal", FakeSession)
    monkeypatch.setattr("app.modules.knowledge.tool.set_tenant_scope", lambda *_: None)
    monkeypatch.setattr(
        "app.modules.knowledge.tool.LocalEmbeddingProvider", lambda: object()
    )
    monkeypatch.setattr(
        "app.modules.knowledge.tool.retrieve_evidence",
        lambda **kwargs: [
            EvidenceRef(
                chunk_id=1,
                document_id=1,
                content="客户合同到期后暂停采购。",
                score=0.91,
            )
        ],
    )

    result = RAGTool(
        reranker=FailingReranker(),
        retrieval_policy=RetrievalPolicy(
            policy_id="paragraph_vector_no_rerank_v1",
            chunk_strategies=("paragraph_v1",),
            rerank_enabled=False,
        ),
    ).execute(
        ToolInput(parameters={"question": "客户合同为何影响销售", "company_id": 1})
    )

    assert result.success is True
    assert result.data["retrieval_policy_id"] == "paragraph_vector_no_rerank_v1"
    assert result.data["evidences"][0]["rerank_score"] is None


def test_rag_tool_applies_runtime_database_timeout(monkeypatch):
    captured: dict[str, object] = {}

    class FakeSession:
        def execute(self, statement, parameters) -> None:
            captured["statement"] = str(statement)
            captured["parameters"] = parameters

        def close(self) -> None:
            pass

    monkeypatch.setattr("app.modules.knowledge.tool.SessionLocal", FakeSession)
    monkeypatch.setattr("app.modules.knowledge.tool.set_tenant_scope", lambda *_: None)
    monkeypatch.setattr(
        "app.modules.knowledge.tool.LocalEmbeddingProvider", lambda: object()
    )
    monkeypatch.setattr(
        "app.modules.knowledge.tool.retrieve_evidence", lambda **_kwargs: []
    )

    result = RAGTool(reranker=FakeReranker([])).execute(
        ToolInput(
            parameters={
                "question": "客户合同为何影响销售",
                "company_id": 1,
                "_runtime_database_timeout_ms": 321,
            }
        )
    )

    assert result.success is True
    assert result.data["status"] == "insufficient_evidence"
    assert "set_config" in captured["statement"]
    assert captured["parameters"] == {"timeout_ms": "321"}


def test_sql_tool_name_and_description():
    tool = SQLTool()
    assert tool.name == "sql_query"
    assert isinstance(tool.description, str)
    assert len(tool.description) > 0


def test_sql_tool_missing_parameters():
    tool = SQLTool()
    result = tool.execute(ToolInput(parameters={}))
    assert result.success is False
    assert result.error == "缺少 sql 参数"
    assert result.error_code == "sql_input_missing"
    assert result.repairable is False


def test_sql_tool_passes_business_catalogue_tables_to_executor(monkeypatch):
    captured: dict[str, object] = {}

    def fake_execute_readonly_sql(sql: str, allowed_tables: set[str], **kwargs: object):
        captured["sql"] = sql
        captured["allowed_tables"] = allowed_tables
        captured.update(kwargs)
        return ["revenue"], [(100.0,)]

    monkeypatch.setattr(
        "app.modules.analysis.data.sql_tool.execute_readonly_sql",
        fake_execute_readonly_sql,
    )

    result = SQLTool().execute(
        ToolInput(parameters={"sql": "SELECT o.total_amount FROM sales_orders AS o"})
    )

    assert result.success is True
    assert result.data == {"columns": ["revenue"], "rows": [(100.0,)]}
    assert captured["allowed_tables"] == set(BUSINESS_TABLES)
    assert captured["timeout_ms"] == 10_000


def test_sql_tool_returns_validation_failure_without_database_connection():
    result = SQLTool().execute(
        ToolInput(
            parameters={
                "sql": "SELECT d.content FROM business_documents AS d",
            }
        )
    )

    assert result.success is False
    assert result.error is not None
    assert "不在业务目录" in result.error
    assert result.error_code == "sql_validation_error"
    assert result.repairable is True


def test_sql_tool_marks_grouping_error_as_repairable_semantic_failure(monkeypatch):
    def raise_grouping_error(sql: str, allowed_tables: set[str], **kwargs: object):
        raise GroupingError("column must appear in the GROUP BY clause")

    monkeypatch.setattr(
        "app.modules.analysis.data.sql_tool.execute_readonly_sql", raise_grouping_error
    )

    result = SQLTool().execute(
        ToolInput(
            parameters={
                "sql": "SELECT o.total_amount FROM sales_orders AS o",
            }
        )
    )

    assert result.success is False
    assert result.error == "经营数据查询暂时无法完成。"
    assert result.error_code == "sql_semantic_error"
    assert result.repairable is True


def test_sql_tool_marks_statement_timeout_as_a_distinct_failure(monkeypatch):
    def raise_query_canceled(sql: str, allowed_tables: set[str], **kwargs: object):
        raise QueryCanceled("canceling statement due to statement timeout")

    monkeypatch.setattr(
        "app.modules.analysis.data.sql_tool.execute_readonly_sql", raise_query_canceled
    )

    result = SQLTool().execute(
        ToolInput(
            parameters={
                "sql": "SELECT o.total_amount FROM sales_orders AS o",
            }
        )
    )

    assert result.success is False
    assert result.error_code == "sql_statement_timeout"
    assert result.repairable is True


def test_sql_tool_returns_safe_failure_when_database_execution_raises(monkeypatch):
    def raise_database_error(sql: str, allowed_tables: set[str], **kwargs: object):
        raise RuntimeError("column must appear in the GROUP BY clause")

    monkeypatch.setattr(
        "app.modules.analysis.data.sql_tool.execute_readonly_sql", raise_database_error
    )

    result = SQLTool().execute(
        ToolInput(
            parameters={
                "sql": "SELECT o.total_amount FROM sales_orders AS o",
            }
        )
    )

    assert result.success is False
    assert result.error == "经营数据查询暂时无法完成。"
    assert result.error_code == "business_db_execution_failed"
    assert result.repairable is False


def test_sql_tool_passes_tenant_source_and_snapshot_catalog_to_executor(monkeypatch):
    captured: dict[str, object] = {}
    catalog = SnapshotCatalog.from_snapshot(
        {
            "tables": {"inventory": [{"name": "on_hand"}]},
            "joins": [],
        }
    )
    source = BusinessDataSource(
        id=4,
        company_id=9,
        name="acme-db",
        dialect="postgresql",
        connection_config={
            "host": "db",
            "port": 5432,
            "database": "acme",
            "user": "readonly",
            "schema": "public",
        },
        credential_env_var="ACME_PASSWORD",
    )

    def fake_execute_readonly_sql(
        sql: str,
        allowed_tables: set[str],
        **kwargs: object,
    ):
        captured["sql"] = sql
        captured["allowed_tables"] = allowed_tables
        captured.update(kwargs)
        return ["on_hand"], [(12,)]

    monkeypatch.setattr(
        "app.modules.analysis.data.sql_tool.execute_readonly_sql", fake_execute_readonly_sql
    )

    result = SQLTool(data_source=source, snapshot_catalog=catalog).execute(
        ToolInput(parameters={"sql": "SELECT i.on_hand FROM inventory AS i"})
    )

    assert result.success is True
    assert captured["allowed_tables"] == {"inventory"}
    assert captured["catalog"] is catalog
    assert captured["data_source"] is source
    assert captured["timeout_ms"] == 10_000


def test_sql_tool_requires_source_and_snapshot_together() -> None:
    catalog = SnapshotCatalog.from_snapshot(
        {"tables": {"inventory": [{"name": "on_hand"}]}, "joins": []}
    )

    try:
        SQLTool(snapshot_catalog=catalog)
        assert False, "missing source should be rejected"
    except ValueError as error:
        assert "必须同时提供" in str(error)
