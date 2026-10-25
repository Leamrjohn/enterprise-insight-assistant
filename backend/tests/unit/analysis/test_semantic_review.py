import json

from app.core.exceptions import RetryableModelError
from app.modules.analysis.catalog.snapshot_catalog import SnapshotCatalog
from app.modules.analysis.data.sql_candidate import SQLCandidate
from app.modules.analysis.planner.planner_decision import PlannerDecision
from app.modules.reporting.semantic_review import EvidenceSemanticReview
from app.modules.reporting.semantic_review_service import SemanticReviewService


class FakeGateway:
    def __init__(self, response: dict) -> None:
        self.response = response
        self.calls: list[dict] = []

    def chat(self, prompt, system_prompt=None, *, json_mode=False) -> str:
        self.calls.append(
            {
                "prompt": prompt,
                "system_prompt": system_prompt,
                "json_mode": json_mode,
            }
        )
        return json.dumps(self.response, ensure_ascii=False)

    def count_tokens(self, text: str) -> int:
        return len(text)


def test_sql_semantic_reviewer_blocks_unrelated_fallback_query() -> None:
    gateway = FakeGateway(
        {
            "decision": "insufficient_schema",
            "reason": "快照没有广告曝光量和点击量。",
            "missing_requirements": ["广告曝光量", "广告点击量"],
        }
    )
    catalog = SnapshotCatalog.from_snapshot(
        {"tables": {"customers": [{"name": "id"}]}, "joins": []}
    )

    decision = SemanticReviewService(gateway=gateway).review_sql(
        question="本月广告点击率是多少？",
        plan={"action": "analyze", "route": "data_only"},
        candidate=SQLCandidate(
            sql='SELECT id AS "客户编号" FROM customers LIMIT 1',
            purpose="无法计算广告点击率",
        ),
        catalog=catalog,
    )

    assert decision.decision == "insufficient_schema"
    assert decision.missing_requirements == ["广告曝光量", "广告点击量"]
    assert gateway.calls[0]["json_mode"] is True
    assert "customers" in gateway.calls[0]["prompt"]


def test_sql_semantic_reviewer_allows_a_hybrid_data_subquestion() -> None:
    gateway = FakeGateway(
        {
            "decision": "execute",
            "reason": "覆盖销售额比较。",
            "missing_requirements": [],
        }
    )
    service = SemanticReviewService(gateway=gateway)

    decision = service.review_sql(
        question="SKU-UNKNOWN-2024 在2024年3月为何下降？",
        plan={
            "route": "hybrid",
            "intent": {
                "required_capabilities": ["产品销售额", "下降原因相关文档"],
            },
        },
        candidate=SQLCandidate(
            sql='SELECT SUM(total_amount) AS "销售额" FROM sales_orders',
            purpose="验证产品销售额比较",
            query_contract={
                "required_concepts": ["产品销售额"],
                "expected_columns": ["销售额"],
                "result_kind": "comparison",
            },
        ),
        catalog=SnapshotCatalog(tables={"sales_orders": {"total_amount"}}, joins=set()),
    )

    assert decision.decision == "execute"
    assert "route=hybrid" in gateway.calls[0]["system_prompt"]
    assert "数据子问题" in gateway.calls[0]["system_prompt"]


def test_plan_semantic_reviewer_can_turn_cross_company_query_into_refusal() -> None:
    gateway = FakeGateway(
        {
            "action": "refuse",
            "route": None,
            "reason": "请求明确指向其他公司。",
            "clarification_question": None,
            "response_message": "我只能分析当前公司已授权的数据。",
            "resolved_question": None,
        }
    )

    decision = SemanticReviewService(gateway=gateway).review_plan(
        question="查询 Beta 公司的销售额。",
        proposed_plan={
            "action": "needs_clarification",
            "route": None,
            "reason": "缺少时间范围。",
            "clarification_question": "请补充时间范围。",
            "response_message": None,
            "resolved_question": None,
        },
        catalog=None,
    )

    assert isinstance(decision, PlannerDecision)
    assert decision.action == "refuse"


def test_plan_semantic_reviewer_preserves_initial_plan_for_accept_vocabulary() -> None:
    gateway = FakeGateway(
        {
            "action": "accept",
            "route": None,
            "reason": "初始计划正确。",
            "clarification_question": None,
            "response_message": None,
            "resolved_question": None,
        }
    )
    proposed_plan = {
        "action": "analyze",
        "route": "data_only",
        "reason": "查询订单总数。",
        "clarification_question": None,
        "response_message": None,
        "resolved_question": "当前销售订单总数是多少？",
        "clarification": None,
        "intent": None,
    }

    decision = SemanticReviewService(gateway=gateway).review_plan(
        question="当前销售订单总数是多少？",
        proposed_plan=proposed_plan,
        catalog=None,
    )

    assert (
        decision.model_dump()
        == PlannerDecision.model_validate(proposed_plan).model_dump()
    )


def test_plan_semantic_reviewer_keeps_planner_scope_when_rewrite_omits_it() -> None:
    gateway = FakeGateway(
        {
            "action": "analyze",
            "route": "hybrid",
            "reason": "需要同时核对销量与资料。",
            "clarification_question": None,
            "response_message": None,
            "resolved_question": "某新产品在2024年3月销量下降的业务原因是什么？",
            "clarification": None,
            "intent": {
                "kind": "business_cause",
                "required_capabilities": ["销量", "文档证据"],
                "specified_slots": ["product", "time_range"],
            },
        }
    )
    proposed_plan = {
        "action": "analyze",
        "route": "hybrid",
        "reason": "需要数据和资料。",
        "clarification_question": None,
        "response_message": None,
        "resolved_question": "某新产品在2024年3月销量下降的业务原因是什么？",
        "clarification": None,
        "intent": {
            "kind": "business_cause",
            "required_capabilities": ["销量", "文档证据"],
            "specified_slots": ["product", "time_range"],
        },
        "evaluation_scope": {"entities": ["某新产品"], "period": "2024-03"},
    }

    decision = SemanticReviewService(gateway=gateway).review_plan(
        question=proposed_plan["resolved_question"],
        proposed_plan=proposed_plan,
        catalog=None,
    )

    assert "九字段" in gateway.calls[0]["system_prompt"]
    assert decision.evaluation_scope is not None
    assert decision.evaluation_scope.model_dump() == proposed_plan["evaluation_scope"]


def test_evidence_semantic_reviewer_marks_unrelated_data_as_unsupported() -> None:
    gateway = FakeGateway(
        {
            "verdict": "unsupported",
            "reason": "客户编号不能支持广告点击率。",
            "limitations": ["缺少广告曝光量和点击量。"],
        }
    )

    decision = SemanticReviewService(gateway=gateway).review_evidence(
        question="本月广告点击率是多少？",
        plan={"action": "analyze", "route": "data_only"},
        data_result={"evidence": [{"columns": ["客户编号"], "rows": [[1]]}]},
        knowledge_result={},
        report={"status": "completed"},
    )

    assert isinstance(decision, EvidenceSemanticReview)
    assert decision.verdict == "unsupported"


def test_evidence_semantic_reviewer_keeps_hybrid_data_and_document_scopes_distinct() -> (
    None
):
    gateway = FakeGateway(
        {
            "verdict": "supported",
            "reason": "SQL 覆盖销售额，文档覆盖合同边界。",
            "limitations": [],
            "supported_document_chunk_ids": [42],
            "document_qualifications": [],
        }
    )

    decision = SemanticReviewService(gateway=gateway).review_evidence(
        question="销售额是多少，合同资料能说明什么？",
        plan={"action": "analyze", "route": "hybrid"},
        data_result={"status": "ready", "evidence": [{"rows": [[1847604.72]]}]},
        knowledge_result={"status": "ready", "evidences": [{"chunk_id": 42}]},
        report={"status": "completed"},
    )

    assert decision.verdict == "supported"
    assert "文档未重复 SQL 指标" in gateway.calls[0]["system_prompt"]


def test_semantic_reviewer_retries_a_transient_model_failure() -> None:
    class RetryGateway(FakeGateway):
        def __init__(self) -> None:
            super().__init__(
                {
                    "decision": "execute",
                    "reason": "候选查询满足问题。",
                    "missing_requirements": [],
                }
            )
            self.failed_once = False

        def chat(self, *args, **kwargs):
            if not self.failed_once:
                self.failed_once = True
                raise RetryableModelError("temporary")
            return super().chat(*args, **kwargs)

    waits: list[float] = []
    service = SemanticReviewService(gateway=RetryGateway(), sleeper=waits.append)

    decision = service.review_sql(
        question="销售额是多少？",
        plan={"action": "analyze", "route": "data_only"},
        candidate=SQLCandidate(sql='SELECT 1 AS "销售额"', purpose="查询销售额"),
        catalog=None,
    )

    assert decision.decision == "execute"
    assert service.model_attempts == 2
    assert waits == [1.0]
