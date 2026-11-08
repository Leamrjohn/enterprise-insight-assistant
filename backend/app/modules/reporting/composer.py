"""Deterministically compose a report from already-authorized evidence."""

from __future__ import annotations

from app.modules.analysis.metrics.facts import (
    build_confirmed_facts,
    build_data_evidence,
)
from app.modules.analysis.metrics.facts import (
    render_data_fields as _render_data_fields,
)
from app.modules.analysis.metrics.facts import (
    render_evidence_purpose as _render_evidence_purpose,
)
from app.modules.reporting.schemas import (
    ConfirmedFact,
    DocumentCitation,
    DocumentFinding,
    FinalAnalysisReport,
    Hypothesis,
    Limitation,
    Recommendation,
)


def render_evidence_purpose(purpose: object) -> str:
    """Compatibility export for existing Reviewer rendering."""
    return _render_evidence_purpose(purpose)


def render_data_fields(columns: list[str], row: list[object]) -> str:
    """Compatibility export for existing Reviewer rendering."""
    return _render_data_fields(columns, row)


def compose_report(
    *,
    data_result: dict,
    knowledge_result: dict,
    route: str | None,
) -> FinalAnalysisReport:
    data_evidence = build_data_evidence(data_result)
    facts = build_confirmed_facts(data_evidence)
    knowledge_answer = knowledge_result.get("answer")
    citations = _document_citations(knowledge_result, knowledge_answer)
    document_findings = _document_findings(
        route=route,
        citations=citations,
        knowledge_answer=knowledge_answer,
    )
    data_failed = data_result.get("status") == "failed"
    knowledge_failed = knowledge_result.get("status") == "failed"

    hypotheses = _hypotheses(facts, citations, knowledge_answer)
    limitations = _limitations(
        facts=facts,
        citations=citations,
        route=route,
        data_failed=data_failed,
        knowledge_failed=knowledge_failed,
    )
    status = (
        "completed" if (facts or document_findings) and not limitations else "partial"
    )
    if not facts and not document_findings and data_failed and not citations:
        status = "failed"

    recommendations = _recommendations(facts, hypotheses) if facts else []
    summary = _summary(status, facts, document_findings, hypotheses, limitations)
    return FinalAnalysisReport(
        status=status,
        executive_summary=summary,
        confirmed_facts=facts,
        hypotheses=hypotheses,
        recommendations=recommendations,
        data_evidence=data_evidence,
        document_citations=citations,
        document_findings=document_findings,
        limitations=limitations,
    )


def _document_citations(
    knowledge_result: dict,
    knowledge_answer: object,
) -> list[DocumentCitation]:
    citations: list[DocumentCitation] = []
    for evidence in knowledge_result.get("evidences") or []:
        chunk_id = evidence.get("chunk_id")
        content = evidence.get("content")
        if not isinstance(content, str) or not content:
            content = knowledge_answer
        if not isinstance(chunk_id, int) or not isinstance(content, str) or not content:
            continue
        citations.append(
            DocumentCitation(
                chunk_id=chunk_id,
                document_id=evidence.get("document_id"),
                excerpt=content,
                score=evidence.get("rerank_score", evidence.get("score")),
            )
        )
    return citations


def _hypotheses(
    facts: list[ConfirmedFact],
    citations: list[DocumentCitation],
    knowledge_answer: object,
) -> list[Hypothesis]:
    if not facts or not citations or not isinstance(knowledge_answer, str):
        return []
    return [
        Hypothesis(
            hypothesis_id="hypothesis-1",
            statement=f"可能原因（未证实）：{knowledge_answer}",
            related_fact_ids=[fact.fact_id for fact in facts],
            citation_chunk_ids=[citation.chunk_id for citation in citations],
            support_level="low",
        )
    ]


def _document_findings(
    *,
    route: str | None,
    citations: list[DocumentCitation],
    knowledge_answer: object,
) -> list[DocumentFinding]:
    """Prepare a candidate finding; Reviewer grants publication after semantic review."""
    if (
        route not in {"knowledge_only", "hybrid"}
        or not citations
        or not isinstance(knowledge_answer, str)
        or not knowledge_answer.strip()
    ):
        return []
    return [
        DocumentFinding(
            finding_id="document-finding-1",
            statement=knowledge_answer,
            citation_chunk_ids=[citation.chunk_id for citation in citations],
        )
    ]


def _limitations(
    *,
    facts: list[ConfirmedFact],
    citations: list[DocumentCitation],
    route: str | None,
    data_failed: bool,
    knowledge_failed: bool,
) -> list[Limitation]:
    limitations: list[Limitation] = []
    if not facts and route != "knowledge_only":
        limitations.append(
            Limitation(
                code="data_unavailable" if data_failed else "data_empty",
                message="经营数据未返回可确认的数字或记录。",
                next_step="检查数据源、查询范围和所需业务字段后重试。",
            )
        )
    if route != "data_only" and not citations:
        limitations.append(
            Limitation(
                code="knowledge_unavailable"
                if knowledge_failed
                else "insufficient_documents",
                message="未检索到可引用的文档证据，因此未确认原因。",
                next_step="上传或选择与问题时间范围、客户、产品相关的业务资料。",
            )
        )
    return limitations


def _recommendations(
    facts: list[ConfirmedFact], hypotheses: list[Hypothesis]
) -> list[Recommendation]:
    basis_hypothesis_ids = [hypothesis.hypothesis_id for hypothesis in hypotheses]
    return [
        Recommendation(
            recommendation_id="recommendation-1",
            priority="medium",
            action="根据已确认指标建立下钻核验清单，并在下一周期复查变化。",
            rationale="建议仅基于当前已确认数据和已标注的文档线索，不等同于确定归因。",
            basis_fact_ids=[fact.fact_id for fact in facts],
            basis_hypothesis_ids=basis_hypothesis_ids,
            verification_metric="复查同一查询口径下的指标变化及相关文档证据。",
        )
    ]


def _summary(
    status: str,
    facts: list[ConfirmedFact],
    document_findings: list[DocumentFinding],
    hypotheses: list[Hypothesis],
    limitations: list[Limitation],
) -> str:
    if status == "failed":
        return "本次未能取得可确认的经营数据，无法形成经营结论。"
    if status == "partial":
        return "已保留可确认的证据，但资料不足或执行受限，未作确定性归因。"
    if hypotheses:
        return "已确认经营数据事实；文档提供了待进一步核验的可能原因。"
    if document_findings:
        return "已确认可引用的文档事实；未将其扩大为未经证实的因果结论。"
    return "已确认经营数据事实；本次未进入原因归因范围。"
