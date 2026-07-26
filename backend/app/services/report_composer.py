"""Deterministically compose a report from already-authorized evidence."""

from __future__ import annotations

from app.schemas.final_analysis import (
    ConfirmedFact,
    DataEvidence,
    DocumentCitation,
    FinalAnalysisReport,
    Hypothesis,
    Limitation,
    Recommendation,
)


_COLUMN_DISPLAY_NAMES = {
    "order_count": "订单数量",
    "total_orders": "订单数量",
    "total_sales": "销售额",
    "sales_amount": "销售额",
    "revenue": "销售额",
    "total_amount": "订单金额",
    "average_order_value": "平均订单金额",
    "avg_order_value": "平均订单金额",
    "region_name": "区域",
    "region": "区域",
    "customer_name": "客户",
    "customer": "客户",
    "product_name": "产品",
    "product": "产品",
    "month": "月份",
    "order_date": "下单日期",
    "status": "订单状态",
}


def render_evidence_purpose(purpose: object) -> str:
    """Keep internal SQL/table terminology out of user-facing summaries."""
    if not isinstance(purpose, str) or not purpose.strip():
        return "已授权经营数据"
    if any(char.isascii() and char.isalpha() for char in purpose):
        return "已授权经营数据"
    return purpose.strip()


def render_data_fields(columns: list[str], row: list[object]) -> str:
    """Render query rows for business users without exposing raw field names."""
    rendered_fields = []
    for column, value in zip(columns, row):
        normalized = str(column).strip().lower()
        label = _COLUMN_DISPLAY_NAMES.get(normalized)
        if label is None:
            label = (
                str(column)
                if any("\u4e00" <= char <= "\u9fff" for char in str(column))
                else "查询结果"
            )
        if value is None:
            rendered_fields.append(f"{label}未返回")
        else:
            rendered_fields.append(f"{label}为{value}")
    return "，".join(rendered_fields)


def compose_report(
    *,
    data_result: dict,
    knowledge_result: dict,
    route: str | None,
) -> FinalAnalysisReport:
    data_evidence = _data_evidence(data_result)
    facts = _facts_from_data(data_evidence)
    knowledge_answer = knowledge_result.get("answer")
    citations = _document_citations(knowledge_result, knowledge_answer)
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
    status = "completed" if facts and not limitations else "partial"
    if not facts and data_failed and not citations:
        status = "failed"

    recommendations = _recommendations(facts, hypotheses) if facts else []
    summary = _summary(status, facts, hypotheses, limitations)
    return FinalAnalysisReport(
        status=status,
        executive_summary=summary,
        confirmed_facts=facts,
        hypotheses=hypotheses,
        recommendations=recommendations,
        data_evidence=data_evidence,
        document_citations=citations,
        limitations=limitations,
    )


def _data_evidence(data_result: dict) -> list[DataEvidence]:
    result: list[DataEvidence] = []
    for index, evidence in enumerate(data_result.get("evidence") or [], start=1):
        columns = evidence.get("columns") or []
        raw_rows = evidence.get("rows") or []
        result.append(
            DataEvidence(
                evidence_id=f"data-{index}",
                purpose=evidence.get("purpose") or "受控经营数据查询",
                sql=evidence.get("sql"),
                columns=[str(column) for column in columns],
                rows=[list(row) for row in raw_rows],
            )
        )
    return result


def _facts_from_data(data_evidence: list[DataEvidence]) -> list[ConfirmedFact]:
    facts: list[ConfirmedFact] = []
    for evidence in data_evidence:
        for row_index, row in enumerate(evidence.rows[:5], start=1):
            if not evidence.columns or len(row) != len(evidence.columns):
                continue
            fields = render_data_fields(evidence.columns, row)
            facts.append(
                ConfirmedFact(
                    fact_id=f"fact-{len(facts) + 1}",
                    statement=f"{render_evidence_purpose(evidence.purpose)}：{fields}。",
                    data_evidence_ids=[evidence.evidence_id],
                )
            )
    return facts


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


def _limitations(
    *,
    facts: list[ConfirmedFact],
    citations: list[DocumentCitation],
    route: str | None,
    data_failed: bool,
    knowledge_failed: bool,
) -> list[Limitation]:
    limitations: list[Limitation] = []
    if not facts:
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
    hypotheses: list[Hypothesis],
    limitations: list[Limitation],
) -> str:
    if status == "failed":
        return "本次未能取得可确认的经营数据，无法形成经营结论。"
    if status == "partial":
        return "已保留可确认的证据，但资料不足或执行受限，未作确定性归因。"
    if hypotheses:
        return "已确认经营数据事实；文档提供了待进一步核验的可能原因。"
    return "已确认经营数据事实；本次未进入原因归因范围。"
