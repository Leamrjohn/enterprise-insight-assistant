from app.agents.protocol import AgentInput
from app.agents.reviewer import ReviewerAgent, _format_data_result
from app.schemas.semantic_review import EvidenceSemanticReview
from app.services.citation_validator import validate_citations
from app.services.coverage_calculator import calculate_coverage
from app.services.numeric_validator import validate_numbers
from app.services.report_composer import render_evidence_purpose


def test_reviewer_hides_model_answer_when_database_citation_check_fails() -> None:
    calls = []

    def reject_citation(
        answer: str, user_id: int, **kwargs: object
    ) -> tuple[bool, list[int]]:
        calls.append((answer, user_id))
        return False, [42]

    agent = ReviewerAgent(citation_validator=reject_citation)

    result = agent.run(
        AgentInput(
            question="华东销售额为什么下降？",
            user_id=7,
            context={
                "data_result": {
                    "status": "ready",
                    "evidence": [
                        {
                            "purpose": "查询华东销售额变化",
                            "columns": ["change"],
                            "rows": [[-12.5]],
                        }
                    ],
                },
                "knowledge_result": {
                    "status": "ready",
                    "answer": "客户取消续约。",
                    "evidences": [{"chunk_id": 42, "content": "客户取消续约。"}],
                },
            },
        )
    )

    assert "客户取消续约" not in (result.answer or "")
    assert calls and calls[0][1] == 7
    assert result.evidence[0]["answer_validation"]["invalid_citation_ids"] == [42]
    assert result.evidence[0]["report"]["document_citations"] == []


def test_reviewer_formats_all_query_rows_without_silently_cutting_evidence() -> None:
    formatted = _format_data_result(
        {
            "evidence": [
                {
                    "purpose": "查询销售额",
                    "columns": ["total_sales"],
                    "rows": [[1], [2], [3], [4], [5], [6]],
                }
            ]
        }
    )

    assert formatted is not None
    assert "销售额为6" in formatted


def test_coverage_calculator_accepts_workflow_dictionary_evidence() -> None:
    coverage, uncovered = calculate_coverage(
        "客户续约情况", [{"content": "客户尚未完成续约。"}]
    )

    assert coverage >= 0
    assert isinstance(uncovered, list)


def test_business_purpose_with_plain_english_is_not_erased() -> None:
    assert render_evidence_purpose("Q2 Sales Overview") == "Q2 Sales Overview"


def test_numeric_validator_rejects_ten_percent_near_match() -> None:
    valid, errors = validate_numbers("销售额为109。", {"evidence": [{"rows": [[100]]}]})

    assert valid is False
    assert errors


def test_numeric_validator_allows_only_display_precision_rounding() -> None:
    valid, errors = validate_numbers(
        "销售额为100。", {"evidence": [{"rows": [[100.4]]}]}
    )

    assert valid is True
    assert errors == []


def test_numeric_validator_supports_fractional_source_rendered_as_percent() -> None:
    valid, errors = validate_numbers(
        "毛利率为8.2%。", {"evidence": [{"rows": [[0.082]]}]}
    )

    assert valid is True
    assert errors == []


def test_citation_validator_rejects_authorized_but_unretrieved_chunk_without_db() -> (
    None
):
    valid, invalid_ids = validate_citations(
        "文档说明：[引用:99]", user_id=7, allowed_chunk_ids={42}
    )

    assert valid is False
    assert invalid_ids == [99]


def test_reviewer_hides_document_answer_when_semantic_reviewer_marks_it_partial() -> (
    None
):
    class PartialSemanticReviewer:
        def review_evidence(self, **kwargs: object) -> EvidenceSemanticReview:
            return EvidenceSemanticReview(
                verdict="partial", reason="资料只描述背景。", limitations=[]
            )

    agent = ReviewerAgent(
        semantic_reviewer=PartialSemanticReviewer(),
        citation_validator=lambda *args, **kwargs: (True, []),
    )
    result = agent.run(
        AgentInput(
            question="销售额为何下降？",
            user_id=7,
            context={
                "semantic_review_enabled": True,
                "data_result": {"status": "failed"},
                "knowledge_result": {
                    "answer": "客户取消续约。",
                    "evidences": [{"chunk_id": 42, "content": "资料背景。"}],
                },
            },
        )
    )

    assert "客户取消续约" not in (result.answer or "")
    assert result.evidence[0]["report"]["document_citations"] == []
