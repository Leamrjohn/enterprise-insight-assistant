from app.modules.analysis.agent_protocol import AgentInput
from app.modules.reporting.citation_validation import validate_citations
from app.modules.reporting.composer import render_evidence_purpose
from app.modules.reporting.coverage import calculate_coverage
from app.modules.reporting.numeric_validation import validate_numbers
from app.modules.reporting.reviewer_agent import ReviewerAgent, _format_data_result
from app.modules.reporting.semantic_review import EvidenceSemanticReview


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


def test_reviewer_does_not_treat_model_generated_purpose_as_fact() -> None:
    assert render_evidence_purpose("资料未提供销售额，因此无法回答。") == "已授权经营数据"


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


def test_numeric_validator_uses_the_deterministic_query_label() -> None:
    valid, errors = validate_numbers(
        "数据查询（已授权经营数据）：订单数量为42。",
        {"evidence": [{"purpose": "2025年8月订单数量", "rows": [[42]]}]},
    )

    assert valid is True
    assert errors == []


def test_numeric_validator_allows_a_number_in_retrieved_cited_text() -> None:
    valid, errors = validate_numbers(
        "资料显示合同于2025年7月到期。",
        {},
        knowledge_evidences=[{"content": "合同于2025年7月到期，客户暂停常规采购。"}],
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


def test_reviewer_skips_model_semantic_review_when_all_evidence_is_insufficient() -> (
    None
):
    class UnexpectedSemanticReviewer:
        def review_evidence(self, **kwargs: object) -> EvidenceSemanticReview:
            raise AssertionError("empty evidence must not call semantic review")

    result = ReviewerAgent(
        semantic_reviewer=UnexpectedSemanticReviewer(),
    ).run(
        AgentInput(
            question="请列出资料支持SUP-003传感器批次异常的依据。",
            user_id=7,
            context={
                "semantic_review_enabled": True,
                "plan": {
                    "route": "knowledge_only",
                    "intent": {"kind": "document_question"},
                },
                "data_result": {"status": "not_run", "evidence": []},
                "knowledge_result": {
                    "status": "insufficient_evidence",
                    "answer": "无法回答：资料不足",
                    "evidences": [],
                },
            },
        )
    )

    assert result.success is True
    assert result.evidence[0]["review_status"] == "partial"
    assert result.evidence[0]["report"]["status"] == "partial"
    validation = result.evidence[0]["answer_validation"]
    assert validation["schema_valid"] is True
    assert validation["numbers_valid"] is True
    assert validation["citations_valid"] is True
    assert validation["invalid_citation_ids"] == []
    assert validation["coverage_valid"] is True


def test_reviewer_validates_hybrid_empty_evidence_and_persists_its_limitation() -> None:
    result = ReviewerAgent().run(
        AgentInput(
            question="某新产品在2024年3月销量下降的业务原因是什么？",
            user_id=7,
            context={
                "plan": {"route": "hybrid"},
                "data_result": {
                    "status": "insufficient_evidence",
                    "error": "经营数据未返回可确认的数字或记录。",
                },
                "knowledge_result": {
                    "status": "insufficient_evidence",
                    "answer": "无法回答：资料不足",
                    "evidences": [],
                },
            },
        )
    )

    metadata = result.evidence[0]
    assert metadata["answer_validation"]["schema_valid"] is True
    assert metadata["answer_validation"]["numbers_valid"] is True
    assert metadata["answer_validation"]["citations_valid"] is True
    assert "缺少能够支持原因判断的文档证据。" in metadata["limitations"]
    assert "缺少能够支持原因判断的文档证据。" in [
        item["message"] for item in metadata["report"]["limitations"]
    ]


def test_reviewer_does_not_expose_unverified_numeric_diagnostic_on_insufficient_data() -> None:
    result = ReviewerAgent().run(
        AgentInput(
            question="SKU-UNKNOWN-2024 在2024年3月为何下降？",
            user_id=7,
            context={
                "plan": {"route": "hybrid"},
                "data_result": {
                    "status": "insufficient_evidence",
                    "error": "候选 SQL 的2024年3月销售额为0，尚未获得可确认记录。",
                },
                "knowledge_result": {
                    "status": "insufficient_evidence",
                    "answer": "无法回答：资料不足",
                    "evidences": [],
                },
            },
        )
    )

    assert result.success is True
    assert "2024" not in (result.answer or "")
    assert result.evidence[0]["answer_validation"]["numbers_valid"] is True


def test_reviewer_publishes_a_supported_document_finding_with_a_verbatim_qualification() -> (
    None
):
    class SupportedDocumentSemanticReviewer:
        def review_evidence(self, **kwargs: object) -> EvidenceSemanticReview:
            return EvidenceSemanticReview(
                verdict="supported",
                reason="已引用文档直接支持该问题。",
                limitations=["不应作为完成答案的执行限制。"],
                supported_document_chunk_ids=[42],
                document_qualifications=[
                    {
                        "statement": "文档不支持只归因于其中任一因素。",
                        "citation_chunk_ids": [42],
                    }
                ],
            )

    agent = ReviewerAgent(
        semantic_reviewer=SupportedDocumentSemanticReviewer(),
        citation_validator=lambda *args, **kwargs: (True, []),
    )
    result = agent.run(
        AgentInput(
            question="传动控制毛利压力有哪些被资料支持的因素？",
            user_id=7,
            context={
                "semantic_review_enabled": True,
                "plan": {
                    "route": "knowledge_only",
                    "intent": {"kind": "document_question"},
                },
                "data_result": {"status": "not_run", "evidence": []},
                "knowledge_result": {
                    "status": "ready",
                    "answer": "采购成本上升和折扣扩大是候选因素。",
                    "evidences": [
                        {
                            "chunk_id": 42,
                            "content": "文档不支持只归因于其中任一因素。",
                        }
                    ],
                },
            },
        )
    )

    report = result.evidence[0]["report"]
    assert report["status"] == "completed"
    assert report["limitations"] == []
    assert report["document_findings"][0]["qualifications"] == [
        {
            "statement": "文档不支持只归因于其中任一因素。",
            "citation_chunk_ids": [42],
        }
    ]
    assert "文档不支持只归因于其中任一因素。" in (result.answer or "")


def test_document_question_fails_closed_without_semantic_document_support() -> None:
    result = ReviewerAgent(citation_validator=lambda *args, **kwargs: (True, [])).run(
        AgentInput(
            question="有哪些资料支持CUST-0001暂停采购？",
            user_id=7,
            context={
                "plan": {
                    "route": "knowledge_only",
                    "intent": {"kind": "document_question"},
                },
                "data_result": {"status": "not_run", "evidence": []},
                "knowledge_result": {
                    "status": "ready",
                    "answer": "合同到期且客户暂停常规采购。",
                    "evidences": [
                        {
                            "chunk_id": 42,
                            "content": "合同到期且客户暂停常规采购。",
                        }
                    ],
                },
            },
        )
    )

    assert "合同到期且客户暂停常规采购" not in (result.answer or "")
    assert result.evidence[0]["report"]["status"] == "partial"
    assert result.evidence[0]["report"]["document_findings"] == []


def test_reviewer_discards_a_nonverbatim_document_qualification() -> None:
    class FabricatedQualificationReviewer:
        def review_evidence(self, **kwargs: object) -> EvidenceSemanticReview:
            return EvidenceSemanticReview(
                verdict="supported",
                reason="文档支持。",
                supported_document_chunk_ids=[42],
                document_qualifications=[
                    {
                        "statement": "该客户已正式拒绝续约。",
                        "citation_chunk_ids": [42],
                    }
                ],
            )

    result = ReviewerAgent(
        semantic_reviewer=FabricatedQualificationReviewer(),
        citation_validator=lambda *args, **kwargs: (True, []),
    ).run(
        AgentInput(
            question="有哪些资料支持CUST-0001暂停采购？",
            user_id=7,
            context={
                "semantic_review_enabled": True,
                "plan": {
                    "route": "knowledge_only",
                    "intent": {"kind": "document_question"},
                },
                "data_result": {"status": "not_run", "evidence": []},
                "knowledge_result": {
                    "status": "ready",
                    "answer": "合同到期且客户暂停常规采购。",
                    "evidences": [
                        {
                            "chunk_id": 42,
                            "content": "合同到期且客户暂停常规采购。",
                        }
                    ],
                },
            },
        )
    )

    assert result.evidence[0]["report"]["status"] == "completed"
    assert result.evidence[0]["report"]["document_findings"][0]["qualifications"] == []
    assert "该客户已正式拒绝续约。" not in (result.answer or "")
