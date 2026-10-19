"""工作流节点的数据流测试，不调用真实模型或数据库。"""

from app.core.exceptions import RetryableModelError
from app.modules.analysis.agent_protocol import AgentOutput
from app.modules.analysis.planner_decision import PlannerDecision
from app.modules.organizations.models import BusinessDataSource
from app.modules.workflow import graph as workflow_graph
from app.modules.workflow import nodes as workflow_nodes
from app.modules.workflow.graph import (
    _route_after_planner,
    build_workflow,
)


def test_workflow_can_be_compiled() -> None:
    assert build_workflow().compile() is not None


def test_router_reviewer_retry_reenters_reviewer_with_existing_evidence(
    monkeypatch,
) -> None:
    calls = []
    data_result = {"status": "ready", "evidence": [{"rows": [[1]]}]}
    knowledge_result = {"status": "ready", "evidences": [{"chunk_id": 7}]}

    def fake_reviewer(state):
        calls.append(state["external_retry_count"])
        assert state["data_result"] == data_result
        assert state["knowledge_result"] == knowledge_result
        if len(calls) == 1:
            return {
                "reviewer_outcome": {
                    "status": "retryable_error",
                    "output": {},
                    "error_code": "reviewer_rate_limited",
                    "retry_hint": "retry",
                    "checkpoint_patch": {},
                }
            }
        return {
            "review_result": {"review_status": "complete"},
            "reviewer_outcome": {
                "status": "succeeded",
                "output": {"review_status": "passed"},
                "retry_hint": "stop",
                "checkpoint_patch": {},
            },
            "final_answer": "重试后的报告。",
        }

    monkeypatch.setattr(workflow_graph, "reviewer_node", fake_reviewer)
    workflow = workflow_graph.build_workflow().compile()
    result = workflow.invoke(
        {
            "question": "销售额为什么下降？",
            "user_id": 1,
            "plan": {"action": "analyze", "route": "hybrid"},
            "data_result": data_result,
            "knowledge_result": knowledge_result,
            "review_result": None,
            "reviewer_outcome": None,
            "terminal_result": None,
            "final_answer": None,
            "error": None,
            "resume_next_node": "reviewer_node",
            "external_retry_count": 0,
            "max_external_retries": 2,
            "loop_history": [],
            "routing_action": None,
            "routing_feedback": None,
        }
    )

    assert calls == [0, 1]
    assert result["terminal_result"] == {
        "outcome": "completed",
        "reason": "evidence_complete",
    }
    assert result["final_answer"] == "重试后的报告。"


def test_effective_question_prefers_the_planner_resolution() -> None:
    assert (
        workflow_nodes._effective_question(
            {
                "question": "那华南区呢？",
                "plan": {"resolved_question": "分析华南区 2025 年 8 月销售额变化。"},
            }
        )
        == "分析华南区 2025 年 8 月销售额变化。"
    )


def test_planner_terminal_renders_structured_clarification_instead_of_free_text() -> (
    None
):
    result = workflow_nodes.planner_terminal_node(
        {
            "plan": {
                "action": "needs_clarification",
                "reason": "缺少必要条件。",
                "clarification_question": "无关的旧追问。",
                "clarification": {
                    "missing_slots": ["time_range", "region"],
                    "examples": ["2026年6月", "华东区"],
                },
            }
        }
    )

    assert result["final_answer"] == "请补充时间范围、区域，例如：2026年6月；华东区。"
    assert result["terminal_result"] == {
        "outcome": "needs_clarification",
        "reason": "缺少必要条件。",
        "missing_fields": ["time_range", "region"],
    }
    assert (
        workflow_nodes._effective_question({"question": "销售额是多少？", "plan": None})
        == "销售额是多少？"
    )


def test_run_analysis_uses_planner_node_for_terminal_plan(monkeypatch) -> None:
    """验证编译后的全局图不是绕过 Planner 的测试替身。"""
    context = {
        "version": "1.0",
        "messages": [{"id": 101, "role": "user", "content": "分析华东区销售额"}],
        "history_truncated": False,
    }

    class FakePlannerAgent:
        def run(self, input):
            assert input.question == "写一首诗"
            assert input.user_id == 7
            assert input.context == {"conversation_context": context}
            return AgentOutput(
                success=True,
                attempts={"model_attempts": 2},
                plan={
                    "action": "scope_exit",
                    "route": None,
                    "reason": "不属于经营分析",
                    "clarification_question": None,
                    "response_message": "我目前只处理经营数据和内部资料分析。",
                },
            )

    monkeypatch.setattr(workflow_nodes, "PlannerAgent", FakePlannerAgent)

    result = workflow_graph.run_analysis(
        "写一首诗",
        user_id=7,
        conversation_context=context,
        semantic_review_enabled=False,
    )

    assert result["plan"]["action"] == "scope_exit"
    assert result["planner_result"] == {
        "status": "ready",
        "attempts": {"model_attempts": 2},
    }
    assert result["terminal_result"] == {
        "outcome": "scope_exit",
        "reason": "不属于经营分析",
    }
    assert result["final_answer"] == "我目前只处理经营数据和内部资料分析。"


def test_run_analysis_passes_attachment_context_only_to_planner(monkeypatch) -> None:
    attachment_context = [
        {
            "artifact_version_id": 7,
            "content_trust_level": "untrusted",
            "extracted_text": "attachment-only-runtime-content",
        }
    ]
    checkpoint_patches: list[dict] = []

    class FakePlannerAgent:
        def run(self, input):
            assert input.context["attachment_context"] == attachment_context
            return AgentOutput(
                success=True,
                attempts={"model_attempts": 1},
                plan={
                    "action": "scope_exit",
                    "route": None,
                    "reason": "不属于经营分析",
                    "clarification_question": None,
                    "response_message": "我目前只处理经营数据和内部资料分析。",
                },
            )

    monkeypatch.setattr(workflow_nodes, "PlannerAgent", FakePlannerAgent)

    result = workflow_graph.run_analysis(
        "分析附件",
        user_id=7,
        attachment_context=attachment_context,
        semantic_review_enabled=False,
        checkpoint_callback=lambda _completed, _next, patch: checkpoint_patches.append(
            patch
        ),
    )

    assert result["terminal_result"]["outcome"] == "scope_exit"
    assert checkpoint_patches
    assert all(
        "attachment-only-runtime-content" not in str(patch)
        for patch in checkpoint_patches
    )


def test_run_analysis_passes_retry_context_only_to_resumed_planner(monkeypatch) -> None:
    retry_context = {
        "failed_node": "planner_node",
        "error_code": "planner_model_retryable_error",
        "retry_number": 2,
    }

    class FakePlannerAgent:
        def run(self, input):
            assert input.context == {
                "conversation_context": None,
                "retry_context": retry_context,
            }
            return AgentOutput(
                success=True,
                attempts={"model_attempts": 1},
                plan={
                    "action": "scope_exit",
                    "route": None,
                    "reason": "不属于经营分析",
                    "clarification_question": None,
                    "response_message": "我目前只处理经营数据和内部资料分析。",
                },
            )

    monkeypatch.setattr(workflow_nodes, "PlannerAgent", FakePlannerAgent)

    result = workflow_graph.run_analysis(
        "写一首诗",
        user_id=7,
        semantic_review_enabled=False,
        resume_next_node="planner_node",
        resume_state={"retry_context": retry_context},
    )

    assert result["terminal_result"]["outcome"] == "scope_exit"


def test_planner_router_rejects_unknown_or_incomplete_plans() -> None:
    invalid_states = [
        {"plan": {}},
        {"plan": {"action": "analyze", "route": None}},
        {"plan": {"action": "analyze", "route": "unknown"}},
        {"plan": {"action": "unknown", "route": None}},
        {"plan": {"action": None, "route": None}},
    ]

    for state in invalid_states:
        assert _route_after_planner(state) == "planning_failure_node"


def test_planner_router_does_not_repair_a_recorded_planner_failure() -> None:
    assert (
        _route_after_planner(
            {
                "plan": None,
                "planner_failure": {
                    "code": "planner_invalid_output",
                    "retryable": False,
                },
            }
        )
        == "planning_failure_node"
    )


def test_planner_node_keeps_attempts_when_planner_failed(monkeypatch) -> None:
    class FakePlannerAgent:
        def run(self, input):
            return AgentOutput(
                success=False,
                error="模型连续返回无效 JSON",
                error_code="planner_invalid_output",
                attempts={"model_attempts": 2},
            )

    monkeypatch.setattr(workflow_nodes, "PlannerAgent", FakePlannerAgent)

    result = workflow_nodes.planner_node(
        {"question": "华东区销售额是多少？", "user_id": 1}
    )

    assert result["planner_result"] == {
        "status": "failed",
        "attempts": {"model_attempts": 2},
    }
    assert result["planner_failure"]["code"] == "planner_invalid_output"


def test_planner_semantic_review_can_replace_an_unsafe_initial_plan(
    monkeypatch,
) -> None:
    class FakeSemanticReviewService:
        model_attempts = 1

        def review_plan(self, **kwargs):
            assert kwargs["question"] == "查询 Beta 公司的销售额。"
            return PlannerDecision(
                action="refuse",
                route=None,
                reason="明确请求其他公司数据。",
                clarification_question=None,
                response_message="我只能分析当前公司已授权的数据。",
                resolved_question=None,
            )

    monkeypatch.setattr(
        workflow_nodes,
        "SemanticReviewService",
        FakeSemanticReviewService,
    )

    result = workflow_nodes.planner_semantic_review_node(
        {
            "question": "查询 Beta 公司的销售额。",
            "semantic_review_enabled": True,
            "plan": {
                "action": "needs_clarification",
                "route": None,
                "reason": "缺少时间范围。",
                "clarification_question": "请补充时间范围。",
                "response_message": None,
                "resolved_question": None,
            },
            "planner_result": {"attempts": {"model_attempts": 1}},
        }
    )

    assert result["plan"]["action"] == "refuse"
    assert result["planner_result"]["attempts"] == {
        "model_attempts": 1,
        "semantic_review_attempts": 1,
    }


def test_planner_semantic_review_stops_analysis_without_structured_intent(
    monkeypatch,
) -> None:
    class FakeSemanticReviewService:
        model_attempts = 1

        def review_plan(self, **kwargs):
            return PlannerDecision(
                action="analyze",
                route="data_only",
                reason="查询订单总数。",
                clarification_question=None,
                response_message=None,
                resolved_question="当前订单总数是多少？",
            )

    monkeypatch.setattr(
        workflow_nodes, "SemanticReviewService", FakeSemanticReviewService
    )

    result = workflow_nodes.planner_semantic_review_node(
        {
            "question": "当前订单总数是多少？",
            "semantic_review_enabled": True,
            "plan": {"action": "analyze", "route": "data_only"},
            "planner_result": {"attempts": {"model_attempts": 1}},
        }
    )

    assert result["plan"]["action"] == "needs_clarification"
    assert result["planner_result"]["status"] == "intent_contract_missing"


def test_planner_semantic_review_cannot_expand_document_evidence_to_data(
    monkeypatch,
) -> None:
    class FakeSemanticReviewService:
        model_attempts = 1

        def review_plan(self, **kwargs):
            assert kwargs["question"] == "有哪些资料支持CUST-0001暂停采购？"
            return PlannerDecision(
                action="analyze",
                route="hybrid",
                reason="需要结合经营数据和资料判断原因。",
                clarification_question=None,
                response_message=None,
                resolved_question="有哪些资料支持CUST-0001暂停采购？",
                intent={
                    "kind": "business_cause",
                    "required_capabilities": ["销售数据", "合同资料"],
                    "specified_slots": ["customer"],
                },
            )

    monkeypatch.setattr(
        workflow_nodes, "SemanticReviewService", FakeSemanticReviewService
    )

    result = workflow_nodes.planner_semantic_review_node(
        {
            "question": "有哪些资料支持CUST-0001暂停采购？",
            "semantic_review_enabled": True,
            "plan": {
                "action": "analyze",
                "route": "knowledge_only",
                "reason": "需要检索已授权合同资料。",
                "clarification_question": None,
                "response_message": None,
                "resolved_question": "有哪些资料支持CUST-0001暂停采购？",
                "intent": {
                    "kind": "document_question",
                    "required_capabilities": ["document_evidence"],
                    "specified_slots": ["customer"],
                },
            },
            "planner_result": {"attempts": {"model_attempts": 1}},
        }
    )

    assert result["plan"]["route"] == "knowledge_only"
    assert result["plan"]["intent"]["kind"] == "document_question"
    assert _route_after_planner(result) == "knowledge_node"


def test_retryable_semantic_review_failure_enters_the_worker_retry_path(
    monkeypatch,
) -> None:
    class FakeSemanticReviewService:
        model_attempts = 1

        def review_plan(self, **kwargs):
            raise RetryableModelError("temporary model outage")

    checkpoints: list[tuple[str, str | None, dict]] = []
    monkeypatch.setattr(
        workflow_nodes, "SemanticReviewService", FakeSemanticReviewService
    )

    result = workflow_nodes.planner_semantic_review_node(
        {
            "question": "本月销售额是多少？",
            "semantic_review_enabled": True,
            "plan": {"action": "analyze", "route": "data_only"},
            "planner_result": {"attempts": {"model_attempts": 1}},
            "checkpoint_callback": lambda completed, next_node, state: (
                checkpoints.append((completed, next_node, state))
            ),
        }
    )

    assert result["semantic_review_outcome"]["status"] == "retryable_error"
    assert result["plan"] is None
    assert _route_after_planner(result) == "planning_failure_node"
    assert result["planner_failure"] == {
        "code": "semantic_review_failed",
        "message": "Planner 语义复核失败: temporary model outage",
        "retryable": True,
    }
    assert len(checkpoints) == 1
    assert checkpoints[0][0:2] == (
        "planner_semantic_review_node",
        "planning_failure_node",
    )


def test_data_node_maps_semantic_schema_gap_to_insufficient_evidence(
    monkeypatch,
) -> None:
    class FakeDataAgent:
        def run(self, input):
            assert input.context["semantic_review_enabled"] is True
            return AgentOutput(
                success=False,
                error="快照没有广告点击量。",
                error_code="insufficient_schema",
                evidence=[{"missing_requirements": ["广告点击量"]}],
            )

    monkeypatch.setattr(workflow_nodes, "DataAgent", FakeDataAgent)

    result = workflow_nodes.data_node(
        {
            "question": "广告点击率是多少？",
            "user_id": 1,
            "semantic_review_enabled": True,
            "plan": {"route": "data_only"},
        }
    )

    assert result["data_result"]["status"] == "insufficient_evidence"
    assert result["data_result"]["candidate"]["missing_requirements"] == ["广告点击量"]


def test_data_node_keeps_feedback_when_semantic_review_is_enabled(monkeypatch) -> None:
    retry_context = {
        "failed_node": "data_node",
        "error_code": "business_db_execution_failed",
        "retry_number": 1,
    }

    class FakeDataAgent:
        def run(self, input):
            assert input.context == {
                "plan": {"route": "data_only"},
                "semantic_review_enabled": True,
                "feedback": {"target": "data", "mode": "replay_validated_sql"},
                "retry_context": retry_context,
            }
            return AgentOutput(
                success=False,
                error="连接失败",
                error_code="business_db_execution_failed",
            )

    monkeypatch.setattr(workflow_nodes, "DataAgent", FakeDataAgent)

    workflow_nodes.data_node(
        {
            "question": "销售额是多少？",
            "user_id": 1,
            "semantic_review_enabled": True,
            "plan": {"route": "data_only"},
            "routing_feedback": {"target": "data", "mode": "replay_validated_sql"},
            "retry_context": retry_context,
        }
    )


def test_knowledge_node_preserves_insufficient_evidence_error_code(monkeypatch) -> None:
    retry_context = {
        "failed_node": "knowledge_node",
        "error_code": "knowledge_retrieval_failed",
        "retry_number": 1,
    }

    class FakeKnowledgeAgent:
        def run(self, input):
            assert input.context["retry_context"] == retry_context
            return AgentOutput(
                success=True,
                answer="资料不足",
                evidence=[],
                error_code="insufficient_evidence",
            )

    monkeypatch.setattr(workflow_nodes, "KnowledgeAgent", FakeKnowledgeAgent)

    result = workflow_nodes.knowledge_node(
        {"question": "为什么下降？", "user_id": 1, "retry_context": retry_context}
    )

    assert result["knowledge_result"]["status"] == "insufficient_evidence"
    assert result["knowledge_result"]["error_code"] == "insufficient_evidence"


def test_planner_router_accepts_only_known_terminal_actions() -> None:
    for action in ("direct_response", "scope_exit", "needs_clarification", "refuse"):
        assert _route_after_planner({"plan": {"action": action}}) == (
            "planner_terminal_node"
        )


def test_data_node_uses_question_instead_of_plan_sql(monkeypatch) -> None:
    captured = {}

    class FakeDataAgent:
        def run(self, input):
            captured["input"] = input
            return AgentOutput(
                success=True,
                evidence=[
                    {
                        "sql": "SELECT o.total_amount FROM sales_orders AS o",
                        "purpose": "查询销售额",
                        "columns": ["total_amount"],
                        "rows": [(100.0,)],
                    }
                ],
            )

    monkeypatch.setattr(workflow_nodes, "DataAgent", FakeDataAgent)

    result = workflow_nodes.data_node(
        {
            "question": "销售额是多少？",
            "user_id": 1,
            "plan": {"sql": "SELECT should_not_be_used"},
        }
    )

    assert captured["input"].question == "销售额是多少？"
    assert captured["input"].user_id == 1
    assert captured["input"].context == {}
    assert result["data_result"]["evidence"][0]["purpose"] == "查询销售额"
    assert result["data_result"]["attempts"] == {}


def test_data_node_records_agent_failure(monkeypatch) -> None:
    class FakeDataAgent:
        def run(self, input):
            return AgentOutput(
                success=False,
                error="模型输出不符合契约",
                error_code="sql_generation_invalid_output",
            )

    monkeypatch.setattr(workflow_nodes, "DataAgent", FakeDataAgent)

    result = workflow_nodes.data_node({"question": "销售额是多少？", "user_id": 1})

    assert result["data_result"] == {
        "status": "failed",
        "error": "模型输出不符合契约",
        "error_code": "sql_generation_invalid_output",
        "attempts": {},
        "candidate": None,
    }
    assert result["data_outcome"]["status"] == "retryable_error"
    assert result["data_outcome"]["retry_hint"] == "retry"
    assert result["error"] == "模型输出不符合契约"


def test_data_node_builds_agent_with_company_source_and_snapshot(monkeypatch) -> None:
    captured: dict[str, object] = {}
    source = BusinessDataSource(
        id=4,
        company_id=9,
        name="acme-db",
        dialect="postgresql",
        connection_config={
            "host": "db",
            "port": 5432,
            "database": "acme",
            "user": "readonly",
            "schema": "public",
        },
        credential_env_var="ACME_PASSWORD",
    )
    snapshot = {
        "tables": {"inventory": [{"name": "on_hand"}]},
        "joins": [],
    }

    class FakeDataAgent:
        def __init__(self, *, data_source, snapshot_catalog) -> None:
            captured["data_source"] = data_source
            captured["snapshot_catalog"] = snapshot_catalog

        def run(self, input):
            return AgentOutput(success=True, evidence=[])

    monkeypatch.setattr(workflow_nodes, "DataAgent", FakeDataAgent)

    result = workflow_nodes.data_node(
        {
            "question": "库存还有多少？",
            "user_id": 1,
            "business_data_source": source,
            "schema_catalog": snapshot,
        }
    )

    assert result["data_result"]["status"] == "ready"
    assert captured["data_source"] is source
    assert captured["snapshot_catalog"].tables == {"inventory": frozenset({"on_hand"})}


def test_data_checkpoint_keeps_the_prior_planner_contract(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeDataAgent:
        def run(self, input):
            return AgentOutput(success=True, evidence=[{"rows": [[100]]}])

    monkeypatch.setattr(workflow_nodes, "DataAgent", FakeDataAgent)
    workflow_nodes.data_node(
        {
            "question": "销售额是多少？",
            "user_id": 1,
            "plan": {"action": "analyze", "route": "data_only"},
            "planner_result": {"status": "ready"},
            "checkpoint_callback": lambda completed, next_node, patch: captured.update(
                completed=completed, next_node=next_node, patch=patch
            ),
        }
    )

    assert captured["completed"] == "data_node"
    assert captured["next_node"] == "reviewer_node"
    assert captured["patch"] == {
        "plan": {"action": "analyze", "route": "data_only"},
        "planner_result": {"status": "ready"},
        "data_result": {
            "status": "ready",
            "evidence": [{"rows": [[100]]}],
            "attempts": {},
        },
        "confirmed_facts": [],
        "data_outcome": {
            "status": "succeeded",
            "output": {
                "status": "ready",
                "evidence": [{"rows": [[100]]}],
                "attempts": {},
            },
            "error_code": None,
            "retry_hint": "stop",
            "checkpoint_patch": {"stage": "querying_data"},
        },
    }


def test_knowledge_node_keeps_answer_and_citations(monkeypatch) -> None:
    class FakeKnowledgeAgent:
        def run(self, input):
            assert input.question == "华东区销售额为什么下降？"
            assert input.user_id == 1
            return AgentOutput(
                success=True,
                answer="客户年度合同到期后未续约。",
                evidence=[
                    {
                        "chunk_id": 42,
                        "document_id": 9,
                        "content": "客户年度合同到期后未续约。",
                        "score": 0.93,
                    }
                ],
            )

    monkeypatch.setattr(workflow_nodes, "KnowledgeAgent", FakeKnowledgeAgent)

    result = workflow_nodes.knowledge_node(
        {"question": "华东区销售额为什么下降？", "user_id": 1}
    )

    assert result["knowledge_result"] == {
        "status": "ready",
        "answer": "客户年度合同到期后未续约。",
        "evidences": [
            {
                "chunk_id": 42,
                "document_id": 9,
                "content": "客户年度合同到期后未续约。",
                "score": 0.93,
            }
        ],
    }
    assert result["knowledge_outcome"]["status"] == "succeeded"


def test_reviewer_node_preserves_final_answer_and_review_evidence(monkeypatch) -> None:
    captured = {}

    class FakeReviewerAgent:
        def run(self, input):
            captured["input"] = input
            return AgentOutput(
                success=True,
                answer="数据与文档证据已汇总。",
                evidence=[
                    {
                        "review_status": "complete",
                        "citation_chunk_ids": [42],
                    }
                ],
            )

    monkeypatch.setattr(workflow_nodes, "ReviewerAgent", FakeReviewerAgent)
    state = {
        "question": "华东区销售额为什么下降？",
        "user_id": 1,
        "data_result": {"evidence": [{"rows": [(-166405.92,)]}]},
        "knowledge_result": {
            "answer": "客户年度合同到期后未续约。",
            "evidences": [{"chunk_id": 42}],
        },
        "retry_context": {
            "failed_node": "reviewer_node",
            "error_code": "reviewer_rate_limited",
            "retry_number": 1,
        },
    }

    result = workflow_nodes.reviewer_node(state)

    assert captured["input"].question == state["question"]
    assert captured["input"].user_id == state["user_id"]
    assert captured["input"].context == {
        "plan": {},
        "data_result": state["data_result"],
        "knowledge_result": state["knowledge_result"],
        "retry_context": state["retry_context"],
    }
    assert result == {
        "review_result": {
            "review_status": "complete",
            "citation_chunk_ids": [42],
            "review_outcome": "passed",
        },
        "final_answer": "数据与文档证据已汇总。",
        "reviewer_outcome": {
            "status": "succeeded",
            "output": {"review_status": "passed"},
            "error_code": None,
            "retry_hint": "stop",
            "checkpoint_patch": {"stage": "composing_report"},
        },
    }


def test_reviewer_node_returns_retryable_outcome_without_revealing_error(
    monkeypatch,
) -> None:
    class FakeReviewerAgent:
        def run(self, input):
            return AgentOutput(
                success=False,
                error="provider retry later",
                error_code="reviewer_rate_limited",
                retryable=True,
            )

    monkeypatch.setattr(workflow_nodes, "ReviewerAgent", FakeReviewerAgent)
    result = workflow_nodes.reviewer_node({"question": "销售额", "user_id": 1})

    assert result["reviewer_outcome"]["status"] == "retryable_error"
    assert result["reviewer_outcome"]["retry_hint"] == "retry"


def test_workflow_runs_data_knowledge_and_reviewer_path(monkeypatch) -> None:
    calls = []

    def fake_planner_node(state):
        calls.append("planner")
        return {
            "plan": {
                "action": "analyze",
                "route": "hybrid",
                "reason": "需要数据和资料。",
                "clarification_question": None,
                "response_message": None,
            }
        }

    def fake_data_node(state):
        calls.append("data")
        return {"data_result": {"evidence": [{"rows": [(-166405.92,)]}]}}

    def fake_knowledge_node(state):
        calls.append("knowledge")
        return {
            "knowledge_result": {
                "answer": "客户年度合同到期后未续约。",
                "evidences": [{"chunk_id": 42}],
            }
        }

    def fake_reviewer_node(state):
        calls.append("reviewer")
        assert state["data_result"] is not None
        assert state["knowledge_result"] is not None
        return {
            "review_result": {"review_status": "complete"},
            "final_answer": "数据与文档证据已汇总。",
        }

    monkeypatch.setattr(workflow_graph, "planner_node", fake_planner_node)
    monkeypatch.setattr(workflow_graph, "data_node", fake_data_node)
    monkeypatch.setattr(workflow_graph, "knowledge_node", fake_knowledge_node)
    monkeypatch.setattr(workflow_graph, "reviewer_node", fake_reviewer_node)

    workflow = workflow_graph.build_workflow().compile()
    result = workflow.invoke(
        {
            "question": "华东区销售额为什么下降？",
            "user_id": 1,
            "plan": None,
            "planner_failure": None,
            "data_result": None,
            "knowledge_result": None,
            "review_result": None,
            "terminal_result": None,
            "final_answer": None,
            "error": None,
        }
    )

    assert calls == ["planner", "data", "knowledge", "reviewer"]
    assert result["final_answer"] == "数据与文档证据已汇总。"
    assert result["review_result"] == {"review_status": "complete"}


def test_workflow_resumes_at_checkpoint_next_node_without_replanning(
    monkeypatch,
) -> None:
    calls = []

    def fail_planner(state):
        raise AssertionError("planner must not rerun after data checkpoint")

    def fake_knowledge(state):
        calls.append("knowledge")
        assert state["data_result"] == {
            "status": "ready",
            "evidence": [{"rows": [[1]]}],
        }
        return {"knowledge_result": {"status": "ready", "evidences": [{"chunk_id": 7}]}}

    def fake_reviewer(state):
        calls.append("reviewer")
        return {
            "review_result": {"review_status": "complete"},
            "final_answer": "已从检查点恢复。",
        }

    monkeypatch.setattr(workflow_graph, "planner_node", fail_planner)
    monkeypatch.setattr(workflow_graph, "knowledge_node", fake_knowledge)
    monkeypatch.setattr(workflow_graph, "reviewer_node", fake_reviewer)
    workflow = workflow_graph.build_workflow().compile()
    result = workflow.invoke(
        {
            "question": "销售额为什么下降？",
            "user_id": 1,
            "plan": {"action": "analyze", "route": "hybrid"},
            "data_result": {"status": "ready", "evidence": [{"rows": [[1]]}]},
            "knowledge_result": None,
            "review_result": None,
            "terminal_result": None,
            "final_answer": None,
            "error": None,
            "resume_next_node": "knowledge_node",
            "external_retry_count": 0,
            "max_external_retries": 2,
            "loop_history": [],
            "data_outcome": None,
            "knowledge_outcome": None,
            "routing_action": None,
            "routing_feedback": None,
            "empty_result_replanned": False,
        }
    )

    assert calls == ["knowledge", "reviewer"]
    assert result["final_answer"] == "已从检查点恢复。"


def test_workflow_keeps_data_failure_for_partial_review_with_document_evidence(
    monkeypatch,
) -> None:
    def fake_planner_node(state):
        return {
            "plan": {
                "action": "analyze",
                "route": "hybrid",
                "reason": "需要经营数据和资料。",
                "clarification_question": None,
                "response_message": None,
            }
        }

    def fake_data_node(state):
        return {
            "data_result": {
                "status": "failed",
                "error": "经营数据查询暂时无法完成。",
                "error_code": "business_db_execution_failed",
                "attempts": {"model_attempts": 1, "sql_attempts": 1},
            }
        }

    def fake_knowledge_node(state):
        return {
            "knowledge_result": {
                "status": "ready",
                "answer": "客户合同到期后尚未续约。",
                "evidences": [{"chunk_id": 42, "document_id": 9}],
            }
        }

    def fake_reviewer_node(state):
        assert state["data_result"] == {
            "status": "failed",
            "error": "经营数据查询暂时无法完成。",
            "error_code": "business_db_execution_failed",
            "attempts": {"model_attempts": 1, "sql_attempts": 1},
        }
        assert state["knowledge_result"]["evidences"] == [
            {"chunk_id": 42, "document_id": 9}
        ]
        return {
            "review_result": {
                "review_status": "partial",
                "data_available": False,
                "knowledge_available": True,
                "citation_chunk_ids": [42],
            },
            "final_answer": "文档线索存在，但经营数据尚未验证。",
        }

    monkeypatch.setattr(workflow_graph, "planner_node", fake_planner_node)
    monkeypatch.setattr(workflow_graph, "data_node", fake_data_node)
    monkeypatch.setattr(workflow_graph, "knowledge_node", fake_knowledge_node)
    monkeypatch.setattr(workflow_graph, "reviewer_node", fake_reviewer_node)

    workflow = workflow_graph.build_workflow().compile()
    result = workflow.invoke(
        {
            "question": "华东区销售额为什么下降？",
            "user_id": 1,
            "plan": None,
            "planner_failure": None,
            "data_result": None,
            "knowledge_result": None,
            "review_result": None,
            "terminal_result": None,
            "final_answer": None,
            "error": None,
        }
    )

    assert result["review_result"]["review_status"] == "partial"
    assert result["final_answer"] == "文档线索存在，但经营数据尚未验证。"


def test_workflow_retries_data_and_reruns_its_downstream_knowledge(
    monkeypatch,
) -> None:
    calls = []

    def fake_planner_node(state):
        calls.append("planner")
        return {
            "plan": {
                "action": "analyze",
                "route": "hybrid",
                "resolved_question": "分析销售额下降原因。",
            },
            "scope_fingerprint": "scope-1",
        }

    def fake_data_node(state):
        calls.append("data")
        if calls.count("data") == 1:
            return {
                "data_result": {
                    "status": "failed",
                    "error_code": "business_db_execution_failed",
                    "candidate": {"sql": "SELECT 1", "purpose": "查询销售额"},
                }
            }
        assert state["routing_feedback"]["mode"] == "replay_validated_sql"
        assert state.get("knowledge_result") is None
        return {"data_result": {"status": "ready", "evidence": [{"rows": [[100]]}]}}

    def fake_knowledge_node(state):
        calls.append("knowledge")
        return {
            "knowledge_result": {
                "status": "ready",
                "answer": "合同尚未续约。",
                "evidences": [{"chunk_id": 7}],
            }
        }

    def fake_reviewer_node(state):
        calls.append("reviewer")
        if calls.count("reviewer") == 1:
            assert state["data_result"]["status"] == "failed"
            return {
                "review_result": {"review_status": "partial"},
                "final_answer": "数据暂时不可用。",
            }
        assert state["knowledge_result"]["evidences"] == [{"chunk_id": 7}]
        return {
            "review_result": {"review_status": "complete"},
            "final_answer": "分析完成。",
        }

    monkeypatch.setattr(workflow_graph, "planner_node", fake_planner_node)
    monkeypatch.setattr(workflow_graph, "data_node", fake_data_node)
    monkeypatch.setattr(workflow_graph, "knowledge_node", fake_knowledge_node)
    monkeypatch.setattr(workflow_graph, "reviewer_node", fake_reviewer_node)

    workflow = workflow_graph.build_workflow().compile()
    result = workflow.invoke(
        {
            "question": "销售额为什么下降？",
            "user_id": 1,
            "company_id": 1,
            "plan": None,
            "planner_failure": None,
            "data_result": None,
            "knowledge_result": None,
            "review_result": None,
            "terminal_result": None,
            "final_answer": None,
            "error": None,
            "conversation_context": None,
            "document_ids": [2],
            "business_data_source": None,
            "schema_catalog": None,
            "semantic_review_enabled": False,
            "scope_fingerprint": None,
            "external_retry_count": 0,
            "max_external_retries": 2,
            "routing_action": None,
            "routing_feedback": None,
            "loop_stop_reason": None,
            "loop_history": [],
            "cached_data_result": None,
            "cached_knowledge_result": None,
            "cache_scope_fingerprint": None,
            "empty_result_replanned": False,
        }
    )

    assert calls == [
        "planner",
        "data",
        "knowledge",
        "reviewer",
        "data",
        "knowledge",
        "reviewer",
    ]
    assert result["external_retry_count"] == 1
    assert result["loop_stop_reason"] == "evidence_complete"


def test_workflow_ends_without_business_agents_for_clarification(monkeypatch) -> None:
    calls = []

    def fake_planner_node(state):
        calls.append("planner")
        return {
            "plan": {
                "action": "needs_clarification",
                "route": None,
                "reason": "缺少范围。",
                "clarification_question": "请补充分析指标和时间范围。",
                "response_message": None,
            }
        }

    def fake_data_node(state):
        calls.append("data")
        return {}

    def fake_knowledge_node(state):
        calls.append("knowledge")
        return {}

    monkeypatch.setattr(workflow_graph, "planner_node", fake_planner_node)
    monkeypatch.setattr(workflow_graph, "data_node", fake_data_node)
    monkeypatch.setattr(workflow_graph, "knowledge_node", fake_knowledge_node)

    workflow = workflow_graph.build_workflow().compile()
    result = workflow.invoke(
        {
            "question": "帮我分析一下",
            "user_id": 1,
            "plan": None,
            "planner_failure": None,
            "data_result": None,
            "knowledge_result": None,
            "review_result": None,
            "terminal_result": None,
            "final_answer": None,
            "error": None,
        }
    )

    assert calls == ["planner"]
    assert result["final_answer"] == "请补充分析指标和时间范围。"
    assert result["terminal_result"] == {
        "outcome": "needs_clarification",
        "reason": "缺少范围。",
    }


def test_planning_failure_keeps_reason_and_retryability() -> None:
    result = workflow_nodes.planning_failure_node(
        {
            "planner_failure": {
                "code": "planner_model_retryable_error",
                "message": "无法生成 Planner 决策: 模型服务超时",
                "retryable": True,
            }
        }
    )

    assert result["final_answer"] == "本次分析暂未完成，请稍后重试。"
    assert result["terminal_result"] == {
        "outcome": "failed",
        "stage": "planning",
        "error_code": "planner_model_retryable_error",
        "retryable": True,
    }


def test_planning_failure_hides_internal_error_after_non_retryable_failure() -> None:
    result = workflow_nodes.planning_failure_node(
        {
            "planner_failure": {
                "code": "planner_invalid_output",
                "message": "模型返回的原始错误细节",
                "retryable": False,
            }
        }
    )

    assert result["final_answer"] == "本次分析暂未完成，请稍后重试。"
    assert "原始错误细节" not in result["final_answer"]
