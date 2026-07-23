"""工作流节点的数据流测试，不调用真实模型或数据库。"""

from app.agents.protocol import AgentOutput
from app.services import workflow_nodes
from app.services import workflow_graph
from app.services.workflow_graph import _route_after_planner, build_workflow


def test_workflow_can_be_compiled() -> None:
    assert build_workflow().compile() is not None


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


def test_planner_router_accepts_only_known_terminal_actions() -> None:
    for action in {"direct_response", "scope_exit", "needs_clarification", "refuse"}:
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

    assert result == {
        "data_result": {
            "status": "failed",
            "error": "模型输出不符合契约",
            "error_code": "sql_generation_invalid_output",
            "attempts": {},
            "candidate": None,
        },
        "error": "模型输出不符合契约",
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

    assert result == {
        "knowledge_result": {
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
    }


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
    }

    result = workflow_nodes.reviewer_node(state)

    assert captured["input"].question == state["question"]
    assert captured["input"].user_id == state["user_id"]
    assert captured["input"].context == {
        "plan": {},
        "data_result": state["data_result"],
        "knowledge_result": state["knowledge_result"],
    }
    assert result == {
        "review_result": {
            "review_status": "complete",
            "citation_chunk_ids": [42],
        },
        "final_answer": "数据与文档证据已汇总。",
    }


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
