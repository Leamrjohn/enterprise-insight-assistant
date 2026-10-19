"""Reviewer Agent —— 检查数据一致性和建议合理性，不替代确定性校验器"""

from collections.abc import Callable

from app.core.exceptions import (
    PermanentModelError,
    RetryableModelError,
    StructuredOutputError,
)
from app.modules.analysis.agent_protocol import Agent, AgentInput, AgentOutput
from app.modules.analysis.tool_protocol import Tool
from app.modules.reporting.composer import (
    compose_report,
    render_data_fields,
    render_evidence_purpose,
)
from app.modules.reporting.coverage import calculate_coverage
from app.modules.reporting.numeric_validation import validate_numbers
from app.modules.reporting.schema_validation import validate_schema
from app.modules.reporting.schemas import (
    DocumentQualification,
    FinalAnalysisReport,
    Limitation,
)
from app.modules.reporting.semantic_review import EvidenceSemanticReview
from app.modules.reporting.semantic_review_service import SemanticReviewService


def _format_data_result(data_result: dict) -> str | None:
    evidences = data_result.get("evidence") or []
    if not evidences:
        return None

    rendered_evidences = []
    for evidence in evidences:
        assessment = evidence.get("result_assessment")
        if isinstance(assessment, dict) and assessment.get("status") != "supported":
            continue
        metric_assessment = evidence.get("metric_assessment")
        if (
            isinstance(metric_assessment, dict)
            and metric_assessment.get("status") != "supported"
        ):
            continue
        claim_assessment = evidence.get("claim_assessment")
        if isinstance(claim_assessment, dict) and claim_assessment.get("status") in {
            "refuted",
            "irrelevant",
        }:
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
    numbers_valid, number_errors = validate_numbers(
        answer,
        data_result,
        knowledge_evidences=knowledge_evidences,
    )
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


def _unsupported_claim_reason(data_result: dict) -> str | None:
    for evidence in data_result.get("evidence") or []:
        assessment = evidence.get("claim_assessment")
        if not isinstance(assessment, dict):
            continue
        status = assessment.get("status")
        if status == "refuted":
            return "受控数据查询结果不支持该数值断言，未将其发布为确认事实。"
        if status == "irrelevant":
            return "查询结果无法支撑该数值断言，未将其发布为确认事实。"
    return None


def _semantic_limitations(review: object) -> list[Limitation]:
    semantic_limitation_messages = getattr(review, "limitations", [])
    reason = getattr(review, "reason", "证据语义复核未通过。")
    limitations = [
        Limitation(
            code="semantic_support_insufficient",
            message=reason,
            next_step="补充语义复核列出的数据、筛选条件或可引用资料后重试。",
        )
    ]
    limitations.extend(
        Limitation(
            code=f"semantic_limitation_{index}",
            message=message,
            next_step="补充或核验该限制涉及的资料后重试。",
        )
        for index, message in enumerate(semantic_limitation_messages, start=1)
        if message.strip()
    )
    return limitations


def _supported_document_chunks(
    *,
    plan: dict,
    semantic_review: EvidenceSemanticReview | None,
    retrieved_chunk_ids: set[int],
) -> set[int] | None:
    intent = plan.get("intent")
    if not isinstance(intent, dict) or intent.get("kind") != "document_question":
        return None
    if semantic_review is None:
        return None
    supported = set(semantic_review.supported_document_chunk_ids)
    if not supported or not supported.issubset(retrieved_chunk_ids):
        return None
    return supported


def _is_document_question(plan: dict) -> bool:
    intent = plan.get("intent")
    return isinstance(intent, dict) and intent.get("kind") == "document_question"


def _verbatim_document_qualifications(
    *,
    semantic_review: EvidenceSemanticReview | None,
    supported_chunk_ids: set[int],
    knowledge_evidences: list[dict],
) -> list[DocumentQualification]:
    """Retain only review boundaries that are verbatim in cited retrieved text."""
    if semantic_review is None:
        return []
    content_by_chunk = {
        evidence["chunk_id"]: evidence.get("content")
        for evidence in knowledge_evidences
        if isinstance(evidence.get("chunk_id"), int)
        and isinstance(evidence.get("content"), str)
    }
    qualifications: list[DocumentQualification] = []
    for proposed in semantic_review.document_qualifications:
        cited_ids = set(proposed.citation_chunk_ids)
        if not cited_ids or not cited_ids.issubset(supported_chunk_ids):
            continue
        if not all(
            proposed.statement in content_by_chunk.get(chunk_id, "")
            for chunk_id in cited_ids
        ):
            continue
        qualifications.append(
            DocumentQualification(
                statement=proposed.statement,
                citation_chunk_ids=sorted(cited_ids),
            )
        )
    return qualifications


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
        if input.context.get("semantic_review_enabled") and (
            data_result.get("evidence") or knowledge_result.get("evidences")
        ):
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
                                *_semantic_limitations(semantic_review),
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
        supported_document_chunk_ids = _supported_document_chunks(
            plan=plan,
            semantic_review=semantic_review,
            retrieved_chunk_ids=set(citation_chunk_ids),
        )
        if supported_document_chunk_ids is not None:
            document_qualifications = _verbatim_document_qualifications(
                semantic_review=semantic_review,
                supported_chunk_ids=supported_document_chunk_ids,
                knowledge_evidences=knowledge_evidences,
            )
            report = report.model_copy(
                update={
                    "document_citations": [
                        citation
                        for citation in report.document_citations
                        if citation.chunk_id in supported_document_chunk_ids
                    ],
                    "document_findings": [
                        finding.model_copy(
                            update={
                                "citation_chunk_ids": sorted(
                                    supported_document_chunk_ids
                                ),
                                "qualifications": document_qualifications,
                            }
                        )
                        for finding in report.document_findings
                    ],
                }
            )
            citation_chunk_ids = sorted(supported_document_chunk_ids)
        semantic_metadata = {
            "semantic_review": (
                semantic_review.model_dump() if semantic_review is not None else None
            ),
            "semantic_review_error": semantic_review_error,
        }
        unsupported_claim_reason = _unsupported_claim_reason(data_result)
        if unsupported_claim_reason is not None:
            return AgentOutput(
                success=True,
                answer=unsupported_claim_reason,
                evidence=[
                    _review_metadata(
                        report,
                        review_status="partial",
                        data_available=True,
                        knowledge_available=bool(citation_chunk_ids),
                        citation_chunk_ids=citation_chunk_ids,
                        limitations=[unsupported_claim_reason],
                        **semantic_metadata,
                    )
                ],
            )
        if (
            (
                _is_document_question(plan)
                or (
                    input.context.get("semantic_review_enabled")
                    and (
                        semantic_review is None
                        or semantic_review.verdict != "supported"
                    )
                )
            )
            and knowledge_answer
            and citation_chunk_ids
            and supported_document_chunk_ids is None
        ):
            report = report.model_copy(
                update={
                    "status": "partial",
                    "hypotheses": [],
                    "document_findings": [],
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
                        "document_findings": [],
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
            qualifications = [
                qualification.statement
                for finding in report.document_findings
                for qualification in finding.qualifications
            ]
            document_prefix = (
                "文档说明："
                if _is_document_question(plan) and report.status == "completed"
                else "文档线索（尚未由当前经营数据验证）："
            )
            answer = f"{document_prefix}{knowledge_answer}\n文档引用：{citations_text}"
            if qualifications:
                answer = f"{answer}\n证据限定：{'；'.join(qualifications)}"
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
                        "document_findings": [],
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
                        review_status=report.status,
                        data_available=False,
                        knowledge_available=True,
                        citation_chunk_ids=citation_chunk_ids,
                        limitations=[
                            limitation.message for limitation in report.limitations
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
            if (
                plan.get("route") == "hybrid"
                and knowledge_result.get("status") == "insufficient_evidence"
            ):
                report = report.model_copy(
                    update={
                        "limitations": [
                            *report.limitations,
                            Limitation(
                                code="document_evidence_insufficient",
                                message="缺少能够支持原因判断的文档证据。",
                                next_step="补充可引用的业务资料后重试原因判断。",
                            ),
                        ]
                    }
                )
            answer = (
                "当前契约快照或可用数据不足以回答该问题。"
                "请补充所需指标或数据源后重试。"
            )
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
                answer=answer if valid else _safe_validation_failure_answer(None),
                evidence=[
                    _review_metadata(
                        report,
                        review_status="partial",
                        data_available=False,
                        knowledge_available=False,
                        citation_chunk_ids=[],
                        limitations=[
                            limitation.message for limitation in report.limitations
                        ],
                        answer_validation=validation,
                        **semantic_metadata,
                    )
                ],
            )

        if knowledge_answer and not knowledge_failed:
            answer = "未检索到可验证引用，无法根据现有文档形成原因判断。"
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
                answer=answer if valid else _safe_validation_failure_answer(None),
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
                        answer_validation=validation,
                        **semantic_metadata,
                    )
                ],
            )
        return AgentOutput(
            success=False,
            error="ReviewerAgent 尚未支持当前证据组合",
        )
