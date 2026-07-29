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
from app.services.coverage_calculator import calculate_coverage
from app.services.numeric_validator import validate_numbers
from app.services.schema_validator import validate_schema
from app.tools.protocol import Tool
from collections.abc import Callable


def _format_data_result(data_result: dict) -> str | None:
    evidences = data_result.get("evidence") or []
    if not evidences:
        return None

    rendered_evidences = []
    for evidence in evidences:
        assessment = evidence.get("result_assessment")
        if isinstance(assessment, dict) and assessment.get("status") != "supported":
            continue
        columns = evidence.get("columns") or []
        rows = evidence.get("rows") or []
        purpose = render_evidence_purpose(evidence.get("purpose"))
        if not columns or not rows:
            rendered_evidences.append(f"数据查询（{purpose}）未返回可展示的记录。")
            continue
        rendered_rows = [render_data_fields(columns, row) for row in rows]
        rendered_evidences.append(f"数据查询（{purpose}）：{'；'.join(rendered_rows)}")

    return "\n".join(rendered_evidences) or None


def _review_metadata(
    report: FinalAnalysisReport,
    **metadata: object,
) -> dict:
    """Keep legacy reviewer metadata while exposing the structured report."""
    return {**metadata, "report": report.model_dump(mode="json")}


def _validate_final_answer(
    *,
    answer: str,
    question: str,
    user_id: int,
    data_result: dict,
    knowledge_evidences: list[dict],
    citation_validator: Callable[..., tuple[bool, list[int]]] | None,
) -> tuple[bool, dict]:
    """Run deterministic guards after composition, before exposing model-derived text."""
    citation_required = bool(knowledge_evidences)
    schema_valid, schema_errors = validate_schema(
        answer,
        len(knowledge_evidences),
        citation_required=citation_required,
    )
    numbers_valid, number_errors = validate_numbers(answer, data_result)
    citations_valid, invalid_citation_ids = (
        citation_validator(
            answer,
            user_id,
            allowed_chunk_ids={
                evidence["chunk_id"]
                for evidence in knowledge_evidences
                if isinstance(evidence.get("chunk_id"), int)
            },
        )
        if citation_required and citation_validator is not None
        else (True, [])
    )
    coverage, uncovered = calculate_coverage(question, knowledge_evidences, answer)
    # Coverage is a diagnostic signal. Citation ownership and parser checks are
    # the hard boundary; a lexical score must not discard otherwise valid evidence.
    coverage_valid = True
    return (
        schema_valid and numbers_valid and citations_valid and coverage_valid,
        {
            "schema_valid": schema_valid,
            "schema_errors": schema_errors,
            "numbers_valid": numbers_valid,
            "number_errors": number_errors,
            "citations_valid": citations_valid,
            "invalid_citation_ids": invalid_citation_ids,
            "coverage": coverage,
            "uncovered_entities": uncovered,
            "coverage_valid": coverage_valid,
        },
    )


def _safe_validation_failure_answer(data_summary: str | None) -> str:
    if data_summary:
        return f"{data_summary}\n文档回答未通过证据校验，未据此作出原因判断。"
    return "现有资料未通过证据校验，无法形成可引用的原因判断。"


class ReviewerAgent(Agent):
    """检查多个 Agent 的结果是否存在冲突，不直接生成新结论"""

    def __init__(
        self,
        semantic_reviewer: SemanticReviewService | None = None,
        *,
        citation_validator: Callable[..., tuple[bool, list[int]]] | None = None,
    ) -> None:
        self._semantic_reviewer = semantic_reviewer
        self._citation_validator = citation_validator

    def set_citation_validator(
        self, validator: Callable[..., tuple[bool, list[int]]]
    ) -> None:
        """Attach the database-backed ownership check at the workflow boundary."""
        self._citation_validator = validator

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
        if (
            input.context.get("semantic_review_enabled")
            and knowledge_answer
            and citation_chunk_ids
            and (semantic_review is None or semantic_review.verdict != "supported")
        ):
            report = report.model_copy(
                update={
                    "status": "partial",
                    "hypotheses": [],
                    "document_citations": [],
                    "limitations": [
                        *report.limitations,
                        Limitation(
                            code="citation_relevance_unverified",
                            message="文档引用未通过问题与回答的语义相关性复核。",
                            next_step="补充直接支撑该问题的资料后重试。",
                        ),
                    ],
                }
            )
            return AgentOutput(
                success=True,
                answer="现有资料未通过问题相关性复核，无法据此形成原因判断。",
                evidence=[
                    _review_metadata(
                        report,
                        review_status="partial",
                        data_available=bool(data_result.get("evidence")),
                        knowledge_available=bool(citation_chunk_ids),
                        citation_chunk_ids=citation_chunk_ids,
                        limitations=(
                            semantic_review.limitations
                            if semantic_review is not None
                            else report.limitations
                        ),
                        **semantic_metadata,
                    )
                ],
            )
        if semantic_review is not None and semantic_review.verdict == "unsupported":
            return AgentOutput(
                success=True,
                answer="现有数据和资料不足以支持回答该问题，请补充相关指标、筛选范围或可引用资料后重试。",
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
            citations_text = " ".join(
                f"[引用:{chunk_id}]" for chunk_id in citation_chunk_ids
            )
            answer = (
                f"{data_summary}\n"
                f"文档说明：{knowledge_answer}\n"
                f"文档引用：{citations_text}"
            )
            valid, validation = _validate_final_answer(
                answer=answer,
                question=input.question,
                user_id=input.user_id,
                data_result=data_result,
                knowledge_evidences=knowledge_evidences,
                citation_validator=self._citation_validator,
            )
            if not valid:
                report = report.model_copy(
                    update={
                        "status": "partial",
                        "hypotheses": [],
                        "document_citations": [],
                        "limitations": [
                            *report.limitations,
                            Limitation(
                                code="final_answer_validation_failed",
                                message="文档回答未通过数值、引用、覆盖率或格式校验。",
                                next_step="补充可验证资料或检查引用后重试。",
                            ),
                        ],
                    }
                )
                answer = _safe_validation_failure_answer(data_summary)

            return AgentOutput(
                success=True,
                answer=answer,
                evidence=[
                    _review_metadata(
                        report,
                        review_status="complete",
                        data_available=True,
                        knowledge_available=True,
                        citation_chunk_ids=citation_chunk_ids,
                        limitations=[],
                        answer_validation=validation,
                        **semantic_metadata,
                    )
                ],
            )
        if data_summary and plan.get("route") == "data_only":
            valid, validation = _validate_final_answer(
                answer=data_summary,
                question=input.question,
                user_id=input.user_id,
                data_result=data_result,
                knowledge_evidences=[],
                citation_validator=self._citation_validator,
            )
            return AgentOutput(
                success=True,
                answer=(
                    data_summary
                    if valid
                    else _safe_validation_failure_answer(data_summary)
                ),
                evidence=[
                    _review_metadata(
                        report,
                        review_status="completed",
                        data_available=True,
                        knowledge_available=False,
                        citation_chunk_ids=[],
                        limitations=[],
                        answer_validation=validation,
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
            answer = f"{data_summary}\n无法根据现有文档说明下降原因。"
            valid, validation = _validate_final_answer(
                answer=answer,
                question=input.question,
                user_id=input.user_id,
                data_result=data_result,
                knowledge_evidences=[],
                citation_validator=self._citation_validator,
            )
            return AgentOutput(
                success=True,
                answer=(
                    answer if valid else _safe_validation_failure_answer(data_summary)
                ),
                evidence=[
                    _review_metadata(
                        report,
                        review_status="partial",
                        data_available=True,
                        knowledge_available=False,
                        citation_chunk_ids=[],
                        limitations=[limitation],
                        answer_validation=validation,
                        **semantic_metadata,
                    )
                ],
            )

        if knowledge_answer and citation_chunk_ids:
            citations_text = " ".join(
                f"[引用:{chunk_id}]" for chunk_id in citation_chunk_ids
            )
            answer = (
                "文档线索（尚未由当前经营数据验证）："
                f"{knowledge_answer}\n文档引用：{citations_text}"
            )
            valid, validation = _validate_final_answer(
                answer=answer,
                question=input.question,
                user_id=input.user_id,
                data_result=data_result,
                knowledge_evidences=knowledge_evidences,
                citation_validator=self._citation_validator,
            )
            if not valid:
                report = report.model_copy(
                    update={
                        "status": "partial",
                        "hypotheses": [],
                        "document_citations": [],
                    }
                )
                answer = _safe_validation_failure_answer(None)
            return AgentOutput(
                success=True,
                answer=answer,
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
                        answer_validation=validation,
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
                answer="未检索到可验证引用，无法根据现有文档形成原因判断。",
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
