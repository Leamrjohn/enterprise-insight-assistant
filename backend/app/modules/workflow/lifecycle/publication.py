"""Map workflow completion facts to task status and report-publication state."""

from dataclasses import dataclass
from typing import Literal

from app.modules.reporting.schemas import FinalAnalysisReport
from app.modules.reviews.service import requires_human_review

PublicationDecision = Literal[
    "published",
    "published_partial",
    "awaiting_human_review",
    "not_published",
    "not_applicable",
]
ReportLocation = Literal["report", "report_draft", "none"]


@dataclass(frozen=True)
class CompletionDecision:
    task_status: str
    attempt_status: str
    publication: PublicationDecision
    report_location: ReportLocation
    reason_code: str

    def publication_record(self) -> dict[str, str]:
        return {
            "decision": self.publication,
            "report_location": self.report_location,
            "reason_code": self.reason_code,
        }


def decide_completion(
    *,
    final_answer: object,
    terminal_outcome: object,
    review_status: object,
    report: FinalAnalysisReport | None,
    company_id: int | None,
) -> CompletionDecision:
    """Keep worker completion separate from publication of a validated report."""
    if terminal_outcome == "needs_clarification":
        return CompletionDecision(
            "needs_clarification",
            "completed",
            "not_applicable",
            "none",
            "needs_clarification",
        )
    if terminal_outcome == "failed" or not isinstance(final_answer, str) or not final_answer:
        return CompletionDecision(
            "failed", "failed", "not_published", "none", "workflow_failed"
        )
    if review_status == "partial" or (report is not None and report.status == "partial"):
        return CompletionDecision(
            "partial",
            "partial",
            "published_partial" if report is not None else "not_published",
            "report" if report is not None else "none",
            "report_partial" if report is not None else "review_partial_without_report",
        )
    if report is not None and company_id is not None and requires_human_review(report):
        return CompletionDecision(
            "awaiting_review",
            "completed",
            "awaiting_human_review",
            "report_draft",
            "causal_hypothesis_requires_human_review",
        )
    if report is not None:
        return CompletionDecision(
            "completed", "completed", "published", "report", "report_validated"
        )
    return CompletionDecision(
        "completed", "completed", "not_applicable", "none", "direct_response"
    )
