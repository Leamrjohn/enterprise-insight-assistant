"""LangGraph 工作流图 —— 把 Agent 节点串成可执行的工作流"""

from typing import Literal

from langgraph.graph import StateGraph, START, END

from app.services.workflow_state import WorkflowState
from app.services.workflow_nodes import (
    planner_node,
    planner_terminal_node,
    planning_failure_node,
    knowledge_node,
    data_node,
    reviewer_node,
)


def _route_after_planner(
    state: WorkflowState,
) -> Literal[
    "data_node",
    "knowledge_node",
    "planner_terminal_node",
    "planning_failure_node",
]:
    """Route valid Planner decisions; never send an invalid plan to an Agent."""
    plan = state.get("plan") or {}
    if not plan:
        if state.get("planner_failure"):
            return "planning_failure_node"
        return "planning_failure_node"

    action = plan.get("action")
    if action == "analyze":
        route = plan.get("route")
        if route in {"data_only", "hybrid"}:
            return "data_node"
        if route == "knowledge_only":
            return "knowledge_node"
        return "planning_failure_node"

    if action in {"direct_response", "scope_exit", "needs_clarification", "refuse"}:
        return "planner_terminal_node"

    return "planning_failure_node"


def _route_after_data(
    state: WorkflowState,
) -> Literal["knowledge_node", "reviewer_node"]:
    """Continue to knowledge only for an LLM-approved hybrid plan."""
    plan = state.get("plan") or {}
    return "knowledge_node" if plan.get("route") == "hybrid" else "reviewer_node"


def build_workflow() -> StateGraph:
    """
    构建工作流图：

    START
      → planner_node ──action/route──→ data_node ──route──→ knowledge_node
                             │                                  │
                             ├──→ knowledge_node ───────────────┤
                             ├──→ planner_terminal_node ────────┤
                             └──→ planning_failure_node ────────┴──→ END
    """
    graph = StateGraph(WorkflowState)

    # 注册所有节点
    graph.add_node("planner_node", planner_node)
    graph.add_node("planner_terminal_node", planner_terminal_node)
    graph.add_node("planning_failure_node", planning_failure_node)
    graph.add_node("data_node", data_node)
    graph.add_node("knowledge_node", knowledge_node)
    graph.add_node("reviewer_node", reviewer_node)

    # 边：START → planner
    graph.add_edge(START, "planner_node")

    # 条件边：Planner 决定分析路线，或安全地结束非分析请求。
    graph.add_conditional_edges(
        "planner_node",
        _route_after_planner,
        {
            "data_node": "data_node",
            "knowledge_node": "knowledge_node",
            "planner_terminal_node": "planner_terminal_node",
            "planning_failure_node": "planning_failure_node",
        },
    )

    # 条件边：只有 hybrid 计划在数据查询后继续检索知识库。
    graph.add_conditional_edges(
        "data_node",
        _route_after_data,
        {
            "knowledge_node": "knowledge_node",
            "reviewer_node": "reviewer_node",
        },
    )

    # 边：knowledge → reviewer
    graph.add_edge("knowledge_node", "reviewer_node")

    # 边：reviewer → END
    graph.add_edge("reviewer_node", END)
    graph.add_edge("planner_terminal_node", END)
    graph.add_edge("planning_failure_node", END)

    return graph


# 编译后的工作流（可直接调用）
workflow = build_workflow().compile()


def run_analysis(
    question: str,
    user_id: int,
    *,
    conversation_context: dict | None = None,
) -> dict:
    """运行一次完整分析"""
    initial_state: WorkflowState = {
        "question": question,
        "user_id": user_id,
        "plan": None,
        "planner_result": None,
        "planner_failure": None,
        "data_result": None,
        "knowledge_result": None,
        "review_result": None,
        "terminal_result": None,
        "final_answer": None,
        "error": None,
        "conversation_context": conversation_context,
    }
    return workflow.invoke(initial_state)
