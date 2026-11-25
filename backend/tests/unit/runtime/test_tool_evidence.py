from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest
from app.modules.analysis.tool_protocol import ToolOutput
from app.modules.runtime.tool_runtime import ToolRuntime
from app.modules.runtime.tools import catalog
from app.modules.runtime.tools.errors import ErrorClass, classify
from app.modules.runtime.tools.evidence import Evidence
from app.modules.runtime.tools.registry import validate_definitions


class _Named:
    def __init__(self, name: str) -> None:
        self.name = name


SQL_RESULT = {
    "columns": ["region", "revenue", "day"],
    # The driver returns tuples with Decimal and date values.
    "rows": [("华东", Decimal("12.50"), date(2025, 8, 1))],
}
RAG_RESULT = {
    "status": "ready",
    "retrieval_policy_id": "paragraph_jieba_rrf_rerank_v1",
    "degraded": True,
    "evidences": [
        {
            "chunk_id": 7,
            "document_id": 3,
            "content": "坏账准备按账龄计提。",
            "score": 0.82,
            "document_name": "财务制度",
        }
    ],
}


def _with_evidence(name: str, data) -> ToolOutput:
    return ToolRuntime._with_evidence(_Named(name), ToolOutput(success=True, data=data))


def test_sql_result_becomes_one_table_and_keeps_its_data():
    result = _with_evidence("sql_query", SQL_RESULT)

    assert result.success
    assert result.data is SQL_RESULT  # validation never rewrites what agents read
    assert result.evidence == [
        Evidence(
            kind="table",
            source_tool="sql_query",
            columns=["region", "revenue", "day"],
            rows=[["华东", Decimal("12.50"), date(2025, 8, 1)]],
        )
    ]


def test_template_result_becomes_one_table():
    data = {**SQL_RESULT, "query_id": "east_revenue", "parameters": {"region": "华东"}}

    (evidence,) = _with_evidence("template_query", data).evidence or []

    assert (evidence.kind, evidence.source_tool) == ("table", "template_query")


def test_each_rag_passage_becomes_one_document_evidence():
    result = _with_evidence("rag_search", RAG_RESULT)

    assert result.evidence == [
        Evidence(
            kind="document",
            source_tool="rag_search",
            document_id=3,
            chunk_id=7,
            excerpt="坏账准备按账龄计提。",
            score=0.82,
        )
    ]


def test_rag_without_evidence_gives_an_empty_list():
    data = {"status": "insufficient_evidence", "answer": "资料不足", "evidences": []}

    assert _with_evidence("rag_search", data).evidence == []


@pytest.mark.parametrize(
    ("name", "data"),
    [
        ("sql_query", {"rows": []}),  # columns missing
        ("sql_query", {"columns": "region", "rows": []}),
        ("rag_search", {"status": "ready"}),  # evidences missing
        ("rag_search", {"status": "unknown", "evidences": []}),
        ("rag_search", None),
    ],
)
def test_a_result_that_breaks_its_contract_becomes_an_infra_failure(name, data):
    result = _with_evidence(name, data)

    assert not result.success
    assert result.error_code == "tool_output_contract_invalid"
    assert classify(result.error_code) is ErrorClass.INFRA


def test_every_registered_runtime_tool_declares_its_contract():
    for definition in catalog.TOOLS:
        assert definition.kind == "runtime"
        assert definition.output_model is not None
        assert definition.to_evidence is not None


SQL = next(d for d in catalog.TOOLS if d.name == "sql_query")


@pytest.mark.parametrize(
    ("definitions", "why"),
    [
        ((replace(SQL, output_model=None),), "runtime without output model"),
        ((replace(SQL, to_evidence=None),), "runtime without evidence"),
        ((replace(SQL, backed_by="rag_search"),), "runtime backed by another"),
        (
            (
                SQL,
                replace(
                    SQL,
                    name="run_sql",
                    contract_version="run_sql/v1",
                    kind="capability",
                    backed_by="missing_tool",
                ),
            ),
            "capability backed by nothing",
        ),
        (
            (
                SQL,
                replace(
                    SQL,
                    name="submit_result",
                    contract_version="submit_result/v1",
                    kind="control",
                    backed_by="sql_query",
                ),
            ),
            "control tool backed by a runtime tool",
        ),
    ],
)
def test_kind_rules_refuse_startup(definitions, why):
    assert validate_definitions(definitions), why


def test_a_capability_backed_by_a_runtime_tool_is_valid():
    run_sql = replace(
        SQL,
        name="run_sql",
        contract_version="run_sql/v1",
        kind="capability",
        backed_by="sql_query",
        output_model=None,
        to_evidence=None,
    )

    assert validate_definitions((SQL, run_sql)) == []
