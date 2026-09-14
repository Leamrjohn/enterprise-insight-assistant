"""The report composer must preserve evidence links and uncertainty boundaries."""

from app.modules.reporting.composer import compose_report


def test_composes_completed_report_with_fact_hypothesis_and_recommendation() -> None:
    report = compose_report(
        route="hybrid",
        data_result={
            "status": "ready",
            "evidence": [
                {
                    "sql": "SELECT revenue FROM monthly_sales",
                    "purpose": "查询华东销售额",
                    "columns": ["revenue"],
                    "rows": [[1847604.72]],
                }
            ],
        },
        knowledge_result={
            "status": "ready",
            "answer": "重点客户合同到期后尚未续约。",
            "evidences": [
                {
                    "chunk_id": 42,
                    "document_id": 9,
                    "content": "重点客户合同到期后尚未续约。",
                    "score": 0.93,
                }
            ],
        },
    )

    assert report.status == "completed"
    assert report.confirmed_facts[0].data_evidence_ids == ["data-1"]
    assert report.hypotheses[0].citation_chunk_ids == [42]
    assert "未证实" in report.hypotheses[0].statement
    assert report.recommendations[0].basis_fact_ids == ["fact-1"]


def test_composes_partial_report_when_documents_are_insufficient() -> None:
    report = compose_report(
        route="hybrid",
        data_result={
            "status": "ready",
            "evidence": [
                {
                    "purpose": "查询销售额",
                    "columns": ["revenue"],
                    "rows": [[100]],
                }
            ],
        },
        knowledge_result={"status": "insufficient_evidence", "evidences": []},
    )

    assert report.status == "partial"
    assert report.confirmed_facts
    assert report.hypotheses == []
    assert report.limitations[0].code == "insufficient_documents"


def test_composes_business_facts_without_raw_english_field_names() -> None:
    report = compose_report(
        route="data_only",
        data_result={
            "status": "ready",
            "evidence": [
                {
                    "purpose": "查询华东区已交付订单",
                    "columns": ["order_count", "total_sales"],
                    "rows": [[841, 54864248.76]],
                }
            ],
        },
        knowledge_result={"status": "ready", "evidences": []},
    )

    statement = report.confirmed_facts[0].statement
    assert "订单数量为841" in statement
    assert "销售额为54864248.76" in statement
    assert "order_count" not in statement
    assert "total_sales" not in statement


def test_hides_technical_query_purpose_and_renders_null_in_business_language() -> None:
    report = compose_report(
        route="data_only",
        data_result={
            "status": "ready",
            "evidence": [
                {
                    "purpose": "使用 shipments 的 delivered_date 判断交付月份",
                    "columns": ["total_sales"],
                    "rows": [[None]],
                }
            ],
        },
        knowledge_result={"status": "ready", "evidences": []},
    )

    statement = report.confirmed_facts[0].statement
    assert "已授权经营数据" in statement
    assert "销售额未返回" in statement
    assert "shipments" not in statement
    assert "delivered_date" not in statement
    assert "None" not in statement


def test_composes_failed_report_without_data_or_document_evidence() -> None:
    report = compose_report(
        route="hybrid",
        data_result={"status": "failed"},
        knowledge_result={"status": "failed"},
    )

    assert report.status == "failed"
    assert report.confirmed_facts == []
    assert report.recommendations == []
    assert report.limitations
