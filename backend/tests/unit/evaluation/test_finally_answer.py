import pytest
from app.modules.reporting.schemas import (
    ConfirmedFact,
    DocumentFinding,
    DocumentQualification,
    FinalAnalysisReport,
    Recommendation,
)
from pydantic import ValidationError


def test_completed_report_rejects_fact_without_data_evidence():
    with pytest.raises(ValidationError, match="事实必须关联已有数据证据"):
        FinalAnalysisReport(
            status="completed",
            executive_summary="This is a summary.",
            confirmed_facts=[
                ConfirmedFact(
                    fact_id="fact1",
                    statement="This is a confirmed fact.",
                    data_evidence_ids=["missing_data"],
                )
            ],
            hypotheses=[],
            recommendations=[],
            data_evidence=[],
            document_citations=[],
            limitations=[],
        )


def test_completed_report_recommendation_without_basis_hypothesis_id():
    with pytest.raises(ValidationError, match="建议必须关联至少一条事实或假设"):
        Recommendation(
            recommendation_id="rec1",
            priority="high",
            action="This is an action.",
            rationale="This is a rationale.",
            basis_fact_ids=[],
            basis_hypothesis_ids=[],
        )


def test_completed_document_finding_can_carry_a_citation_bound_qualification() -> None:
    report = FinalAnalysisReport(
        status="completed",
        executive_summary="资料支持两个候选因素，但不支持单一归因。",
        document_citations=[
            {
                "chunk_id": 42,
                "excerpt": "文档不支持只归因于其中任一因素。",
            }
        ],
        document_findings=[
            DocumentFinding(
                finding_id="document-finding-1",
                statement="采购成本上升和折扣扩大是候选因素。",
                citation_chunk_ids=[42],
                qualifications=[
                    DocumentQualification(
                        statement="文档不支持只归因于其中任一因素。",
                        citation_chunk_ids=[42],
                    )
                ],
            )
        ],
    )

    assert report.status == "completed"
    assert report.limitations == []
    assert report.document_findings[0].qualifications[0].citation_chunk_ids == [42]


def test_document_qualification_rejects_an_uncited_chunk() -> None:
    with pytest.raises(ValidationError, match="文档限定语必须关联已有文档引用"):
        FinalAnalysisReport(
            status="completed",
            executive_summary="测试。",
            document_citations=[{"chunk_id": 42, "excerpt": "已引用。"}],
            document_findings=[
                {
                    "finding_id": "document-finding-1",
                    "statement": "资料支持该结论。",
                    "citation_chunk_ids": [42],
                    "qualifications": [
                        {
                            "statement": "范围限定。",
                            "citation_chunk_ids": [99],
                        }
                    ],
                }
            ],
        )
