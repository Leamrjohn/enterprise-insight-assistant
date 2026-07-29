import pytest

from app.services.report_validator import ReportValidationError, validate_report


def _draft(chunk_id: int = 8) -> dict:
    return {
        "status": "partial",
        "executive_summary": "发现销售下降。",
        "confirmed_facts": [
            {
                "fact_id": "fact-1",
                "statement": "销售下降。",
                "data_evidence_ids": ["data-1"],
            }
        ],
        "hypotheses": [
            {
                "hypothesis_id": "hypothesis-1",
                "statement": "价格调整可能影响销量。",
                "related_fact_ids": ["fact-1"],
                "citation_chunk_ids": [chunk_id],
                "support_level": "low",
            }
        ],
        "recommendations": [],
        "data_evidence": [{"evidence_id": "data-1", "purpose": "固定查询"}],
        "document_citations": [{"chunk_id": chunk_id, "excerpt": "价格调整通知。"}],
        "limitations": [
            {"code": "partial", "message": "资料有限。", "next_step": "补充资料。"}
        ],
    }


def test_report_validator_accepts_schema_and_frozen_citation_scope() -> None:
    assert validate_report(_draft(), allowed_chunk_ids={8}).status == "partial"


def test_report_validator_rejects_citation_outside_frozen_scope() -> None:
    with pytest.raises(ReportValidationError, match="frozen task scope"):
        validate_report(_draft(), allowed_chunk_ids={9})
