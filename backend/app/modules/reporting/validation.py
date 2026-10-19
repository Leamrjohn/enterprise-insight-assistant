"""Final deterministic gate before a report may be persisted or published."""

from collections.abc import Iterable
from typing import Any

from pydantic import ValidationError

from app.modules.reporting.schemas import FinalAnalysisReport


class ReportValidationError(ValueError):
    code = "report_validation_failed"


def validate_report(
    draft: FinalAnalysisReport | dict[str, Any],
    *,
    allowed_chunk_ids: Iterable[int] | None = None,
    allowed_attachment_citation_ids: Iterable[str] | None = None,
) -> FinalAnalysisReport:
    """Validate schema links and the task-frozen citation scope without an LLM."""
    try:
        report = FinalAnalysisReport.model_validate(draft)
    except ValidationError as exc:
        raise ReportValidationError(str(exc)) from exc
    cited = {citation.chunk_id for citation in report.document_citations}
    if allowed_chunk_ids is not None and not cited.issubset(set(allowed_chunk_ids)):
        raise ReportValidationError("report cites chunks outside the frozen task scope")
    attachment_citations = {
        citation.citation_id for citation in report.attachment_citations
    }
    if (
        allowed_attachment_citation_ids is not None
        and not attachment_citations.issubset(set(allowed_attachment_citation_ids))
    ):
        raise ReportValidationError("report cites attachments outside the frozen task scope")
    return report
