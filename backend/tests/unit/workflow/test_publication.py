from app.modules.reporting.schemas import FinalAnalysisReport
from app.modules.workflow.lifecycle.publication import decide_completion


def _report(**overrides: object) -> FinalAnalysisReport:
    values = {
        "status": "completed",
        "executive_summary": "已完成。",
        "confirmed_facts": [
            {
                "fact_id": "fact-1",
                "statement": "销售额为 100。",
                "data_evidence_ids": ["data-1"],
            }
        ],
        "data_evidence": [
            {
                "evidence_id": "data-1",
                "purpose": "销售额",
                "columns": ["销售额"],
                "rows": [[100]],
            }
        ],
    }
    values.update(overrides)
    return FinalAnalysisReport.model_validate(values)


def test_direct_response_completes_without_claiming_a_report_was_published() -> None:
    decision = decide_completion(
        final_answer="我只处理经营问题。",
        terminal_outcome="scope_exit",
        review_status=None,
        report=None,
        company_id=1,
    )

    assert decision.task_status == "completed"
    assert decision.publication == "not_applicable"
    assert decision.report_location == "none"


def test_completed_report_is_published_when_no_human_review_is_required() -> None:
    decision = decide_completion(
        final_answer="已完成。",
        terminal_outcome=None,
        review_status="completed",
        report=_report(),
        company_id=1,
    )

    assert decision.task_status == "completed"
    assert decision.publication == "published"


def test_causal_report_waits_for_human_review_instead_of_publishing() -> None:
    decision = decide_completion(
        final_answer="待审核。",
        terminal_outcome=None,
        review_status="completed",
        report=_report(
            hypotheses=[
                {
                    "hypothesis_id": "hypothesis-1",
                    "statement": "可能原因。",
                    "related_fact_ids": ["fact-1"],
                    "citation_chunk_ids": [1],
                    "support_level": "low",
                }
            ],
            document_citations=[{"chunk_id": 1, "excerpt": "线索。"}],
        ),
        company_id=1,
    )

    assert decision.task_status == "awaiting_review"
    assert decision.publication == "awaiting_human_review"
    assert decision.report_location == "report_draft"


def test_failed_and_partial_paths_do_not_claim_completed_publication() -> None:
    failed = decide_completion(
        final_answer="失败。",
        terminal_outcome="failed",
        review_status=None,
        report=None,
        company_id=1,
    )
    partial = decide_completion(
        final_answer="资料不足。",
        terminal_outcome=None,
        review_status="partial",
        report=None,
        company_id=1,
    )

    assert failed.publication == "not_published"
    assert partial.task_status == "partial"
    assert partial.publication == "not_published"
