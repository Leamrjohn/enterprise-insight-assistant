"""Reviewer Agent —— 检查数据一致性和建议合理性，不替代确定性校验器"""

from app.agents.protocol import Agent, AgentInput, AgentOutput
from app.core.exceptions import (
    PermanentModelError,
    RetryableModelError,
    StructuredOutputError,
)
from app.schemas.final_analysis import FinalAnalysisReport, Limitation
from app.services.semantic_review import SemanticReviewService
from app.services.report_composer import (
    compose_report,
    render_data_fields,
    render_evidence_purpose,
)
from app.tools.protocol import Tool


def _format_data_result(data_result: dict) -> str | None:
    evidences = data_result.get("evidence") or []
    if not evidences:
        return None

    first_evidence = evidences[0]
    assessment = first_evidence.get("result_assessment")
    if isinstance(assessment, dict) and assessment.get("status") != "supported":
        return None
    columns = first_evidence.get("columns") or []
    rows = first_evidence.get("rows") or []
    purpose = render_evidence_purpose(first_evidence.get("purpose"))

    if not columns or not rows:
        return f"数据查询（{purpose}）未返回可展示的记录。"

    rendered_rows = []
    for row in rows[:5]:
        rendered_rows.append(render_data_fields(columns, row))

    return f"数据查询（{purpose}）：{'；'.join(rendered_rows)}"


def _review_metadata(
    report: FinalAnalysisReport,
    **metadata: object,
) -> dict:
    """Keep legacy reviewer metadata while exposing the structured report."""
    return {**metadata, "report": report.model_dump(mode="json")}


class ReviewerAgent(Agent):
    """检查多个 Agent 的结果是否存在冲突，不直接生成新结论"""

    def __init__(self, semantic_reviewer: SemanticReviewService | None = None) -> None:
        self._semantic_reviewer = semantic_reviewer

    @property
    def name(self) -> str:
        return "reviewer"

    @property
    def description(self) -> str:
        return "检查 KnowledgeAgent 和 DataAgent 的结果是否一致"

    @property
    def allowed_tools(self) -> list[Tool]:
        return []  # Reviewer 不调任何工具

    def run(self, input: AgentInput) -> AgentOutput:
        """对比 context 中的两份证据，检查一致性"""
        data_result = input.context.get("data_result") or {}
        knowledge_result = input.context.get("knowledge_result") or {}
        plan = input.context.get("plan") or {}
        if not data_result and not knowledge_result:
            return AgentOutput(
                success=False,
                error="ReviewerAgent 需要 context 中有 data_result 或 knowledge_result",
            )

        report = compose_report(
            data_result=data_result,
            knowledge_result=knowledge_result,
            route=plan.get("route"),
        )

        semantic_review = None
        if input.context.get("semantic_review_enabled"):
            if self._semantic_reviewer is None:
                self._semantic_reviewer = SemanticReviewService()
            try:
                semantic_review = self._semantic_reviewer.review_evidence(
                    question=input.question,
                    plan=plan,
                    data_result=data_result,
                    knowledge_result=knowledge_result,
                    report=report.model_dump(mode="json"),
                )
            except (
                PermanentModelError,
                RetryableModelError,
                StructuredOutputError,
            ) as error:
                semantic_review = None
                semantic_review_error = f"证据语义复核未完成: {error}"
            else:
                semantic_review_error = None
                if semantic_review.verdict != "supported" and report.status != "failed":
                    report = report.model_copy(
                        update={
                            "status": "partial",
                            "limitations": [
                                *report.limitations,
                                Limitation(
                                    code="semantic_support_insufficient",
                                    message=semantic_review.reason,
                                    next_step=(
                                        "补充语义复核列出的数据、筛选条件或可引用资料后重试。"
                                    ),
                                ),
                            ],
                        }
                    )
        else:
            semantic_review_error = None

        data_summary = _format_data_result(data_result)
        data_failed = data_result.get("status") == "failed"
        knowledge_failed = knowledge_result.get("status") == "failed"
        knowledge_evidences = knowledge_result.get("evidences") or []
        knowledge_answer = knowledge_result.get("answer")
        citation_chunk_ids = [
            evidence["chunk_id"]
            for evidence in knowledge_evidences
            if isinstance(evidence.get("chunk_id"), int)
        ]
        semantic_metadata = {
            "semantic_review": (
                semantic_review.model_dump() if semantic_review is not None else None
            ),
            "semantic_review_error": semantic_review_error,
        }
        if semantic_review is not None and semantic_review.verdict == "unsupported":
            return AgentOutput(
                success=True,
                answer=(
                    f"现有数据和资料不足以支持回答该问题。{semantic_review.reason}"
                ),
                evidence=[
                    _review_metadata(
                        report,
                        review_status="partial",
                        data_available=bool(data_result.get("evidence")),
                        knowledge_available=bool(citation_chunk_ids),
                        citation_chunk_ids=citation_chunk_ids,
                        limitations=semantic_review.limitations,
                        **semantic_metadata,
                    )
                ],
            )
        if data_summary and knowledge_answer and citation_chunk_ids:
            citations_text = ", ".join(
                f"chunk_id={chunk_id}" for chunk_id in citation_chunk_ids
            )

            return AgentOutput(
                success=True,
                answer=(
                    f"{data_summary}\n"
                    f"文档说明：{knowledge_answer}\n"
                    f"文档引用：{citations_text}"
                ),
                evidence=[
                    _review_metadata(
                        report,
                        review_status="complete",
                        data_available=True,
                        knowledge_available=True,
                        citation_chunk_ids=citation_chunk_ids,
                        limitations=[],
                        **semantic_metadata,
                    )
                ],
            )
        if data_summary and plan.get("route") == "data_only":
            return AgentOutput(
                success=True,
                answer=data_summary,
                evidence=[
                    _review_metadata(
                        report,
                        review_status="completed",
                        data_available=True,
                        knowledge_available=False,
                        citation_chunk_ids=[],
                        limitations=[],
                        **semantic_metadata,
                    )
                ],
            )
        if data_summary:
            limitation = (
                "文档检索暂时不可用，未对原因作出结论。"
                if knowledge_failed
                else "未检索到足够的文档证据，未对原因作出结论。"
            )
            return AgentOutput(
                success=True,
                answer=f"{data_summary}\n无法根据现有文档说明下降原因。",
                evidence=[
                    _review_metadata(
                        report,
                        review_status="partial",
                        data_available=True,
                        knowledge_available=False,
                        citation_chunk_ids=[],
                        limitations=[limitation],
                        **semantic_metadata,
                    )
                ],
            )

        if knowledge_answer and citation_chunk_ids:
            citations_text = ", ".join(
                f"chunk_id={chunk_id}" for chunk_id in citation_chunk_ids
            )
            return AgentOutput(
                success=True,
                answer=(
                    "文档线索（尚未由当前经营数据验证）："
                    f"{knowledge_answer}\n文档引用：{citations_text}"
                ),
                evidence=[
                    _review_metadata(
                        report,
                        review_status="partial",
                        data_available=False,
                        knowledge_available=True,
                        citation_chunk_ids=citation_chunk_ids,
                        limitations=[
                            "经营数据查询未成功，文档线索不能作为已确认事实。"
                        ],
                        **semantic_metadata,
                    )
                ],
            )

        if data_failed and not citation_chunk_ids:
            return AgentOutput(
                success=True,
                answer=report.executive_summary,
                evidence=[
                    _review_metadata(
                        report,
                        review_status="failed",
                        data_available=False,
                        knowledge_available=False,
                        citation_chunk_ids=[],
                        limitations=["经营数据与文档检索均未成功，无法形成分析结果"],
                        **semantic_metadata,
                    )
                ],
            )

        if data_result.get("status") == "insufficient_evidence":
            return AgentOutput(
                success=True,
                answer=(
                    "当前契约快照或可用数据不足以回答该问题。"
                    f"{data_result.get('error') or '请补充所需指标或数据源后重试。'}"
                ),
                evidence=[
                    _review_metadata(
                        report,
                        review_status="partial",
                        data_available=False,
                        knowledge_available=False,
                        citation_chunk_ids=[],
                        limitations=[data_result.get("error") or "经营数据证据不足。"],
                        **semantic_metadata,
                    )
                ],
            )

        if knowledge_answer and not knowledge_failed:
            return AgentOutput(
                success=True,
                answer=knowledge_answer,
                evidence=[
                    _review_metadata(
                        report,
                        review_status="partial",
                        data_available=False,
                        knowledge_available=False,
                        citation_chunk_ids=[],
                        limitations=[
                            "未检索到足够的文档证据，无法形成可引用的原因判断。"
                        ],
                        **semantic_metadata,
                    )
                ],
            )
        return AgentOutput(
            success=False,
            error="ReviewerAgent 尚未支持当前证据组合",
        )
