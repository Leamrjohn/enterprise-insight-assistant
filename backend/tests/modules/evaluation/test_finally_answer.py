import pytest
from app.modules.reporting.schemas import (
    FinalAnalysisReport,
    ConfirmedFact,
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
