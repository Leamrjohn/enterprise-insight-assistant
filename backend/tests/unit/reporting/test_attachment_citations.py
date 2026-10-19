import hashlib

import pytest

from app.modules.reporting.schemas import build_attachment_citation_id
from app.modules.reporting.validation import ReportValidationError, validate_report


def _attachment_citation(*, start: int = 0, end: int = 12) -> dict[str, object]:
    fragment_hash = hashlib.sha256(b"customer cancelled").hexdigest()
    return {
        "citation_id": build_attachment_citation_id(
            artifact_version_id=7,
            parse_result_id=11,
            char_start=start,
            char_end=end,
            fragment_sha256=fragment_hash,
        ),
        "artifact_version_id": 7,
        "parse_result_id": 11,
        "char_start": start,
        "char_end": end,
        "fragment_sha256": fragment_hash,
    }


def _draft(citation: dict[str, object]) -> dict[str, object]:
    citation_id = str(citation["citation_id"])
    return {
        "schema_version": "1.1",
        "status": "partial",
        "executive_summary": "已确认销售额下降，附件提供待核验线索。",
        "confirmed_facts": [
            {
                "fact_id": "fact-1",
                "statement": "销售额下降。",
                "data_evidence_ids": ["data-1"],
            }
        ],
        "hypotheses": [
            {
                "hypothesis_id": "hypothesis-1",
                "statement": "客户取消续约可能影响销量。",
                "related_fact_ids": ["fact-1"],
                "attachment_citation_ids": [citation_id],
                "support_level": "low",
            }
        ],
        "recommendations": [],
        "data_evidence": [{"evidence_id": "data-1", "purpose": "固定查询"}],
        "document_citations": [],
        "attachment_citations": [citation],
        "limitations": [
            {"code": "partial", "message": "附件线索尚未验证。", "next_step": "补充核验数据。"}
        ],
    }


def test_report_accepts_a_task_scoped_attachment_reference_without_persisting_text() -> None:
    citation = _attachment_citation()

    report = validate_report(
        _draft(citation),
        allowed_attachment_citation_ids={str(citation["citation_id"])},
    )

    serialized = report.model_dump_json()
    assert report.schema_version == "1.1"
    assert "customer cancelled" not in serialized
    assert report.attachment_citations[0].artifact_version_id == 7


def test_report_rejects_an_attachment_reference_outside_the_frozen_scope() -> None:
    with pytest.raises(ReportValidationError, match="attachments outside the frozen task scope"):
        validate_report(
            _draft(_attachment_citation()),
            allowed_attachment_citation_ids=set(),
        )


def test_report_rejects_a_citation_id_that_does_not_match_its_range_or_hash() -> None:
    citation = _attachment_citation()
    citation["char_end"] = 13

    with pytest.raises(ReportValidationError, match="附件引用标识"):
        validate_report(_draft(citation))


def test_report_rejects_attachment_citations_under_the_legacy_schema_version() -> None:
    draft = _draft(_attachment_citation())
    draft["schema_version"] = "1.0"

    with pytest.raises(ReportValidationError, match="schema_version 1.1"):
        validate_report(draft)
