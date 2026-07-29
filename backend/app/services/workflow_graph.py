"""LangGraph 工作流图 —— 把 Agent 节点串成可执行的工作流"""

from collections.abc import Callable
from typing import Literal

from langgraph.graph import StateGraph, START, END

from app.services.workflow_state import WorkflowState
from app.models.company import BusinessDataSource
from app.services.tool_runtime import ToolRuntime
from app.services.workflow_nodes import (
    planner_node,
    planner_semantic_review_node,
    planner_terminal_node,
    planning_failure_node,
    knowledge_node,
    data_node,
    reviewer_node,
    smart_router_node,
)


_RESUMABLE_NODES = frozenset(
    {
        "planner_node",
        "planner_semantic_review_node",
        "planner_terminal_node",
        "planning_failure_node",
        "data_node",
        "knowledge_node",
        "reviewer_node",
        "smart_router_node",
    }
)


def _route_from_start(state: WorkflowState) -> str:
    """Resume only an allow-listed graph node from a database checkpoint."""
    next_node = state.get("resume_next_node")
    return next_node if next_node in _RESUMABLE_NODES else "planner_node"


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
    if (
        state.get("routing_action") == "retry_data"
        and state.get("cached_knowledge_result") is not None
        and state.get("cache_scope_fingerprint") == state.get("scope_fingerprint")
    ):
        return "reviewer_node"
    plan = state.get("plan") or {}
    return "knowledge_node" if plan.get("route") == "hybrid" else "reviewer_node"


def _route_after_smart_router(
    state: WorkflowState,
) -> Literal["data_node", "knowledge_node", "reviewer_node", "planner_node", "end"]:
    action = state.get("routing_action")
    if action == "retry_data":
        return "data_node"
    if action == "retry_knowledge":
        return "knowledge_node"
    if action == "retry_reviewer":
        return "reviewer_node"
    if action == "replan":
        return "planner_node"
    return "end"


def build_workflow() -> StateGraph:
    """
    构建工作流图：

    START
      → planner_node → planner_semantic_review_node ──action/route──→ data_node ──route──→ knowledge_node
                             │                                  │
                             ├──→ knowledge_node ───────────────┤
                             ├──→ planner_terminal_node ────────┤
                             └──→ planning_failure_node ────────┴──→ END
    """
    graph = StateGraph(WorkflowState)

    # 注册所有节点
    graph.add_node("planner_node", planner_node)
    graph.add_node("planner_semantic_review_node", planner_semantic_review_node)
    graph.add_node("planner_terminal_node", planner_terminal_node)
    graph.add_node("planning_failure_node", planning_failure_node)
    graph.add_node("data_node", data_node)
    graph.add_node("knowledge_node", knowledge_node)
    graph.add_node("reviewer_node", reviewer_node)
    graph.add_node("smart_router_node", smart_router_node)

    graph.add_conditional_edges(
        START,
        _route_from_start,
        {node: node for node in _RESUMABLE_NODES},
    )

    graph.add_edge("planner_node", "planner_semantic_review_node")

    # 条件边：经语义复核后的 Planner 决定分析路线，或安全地结束非分析请求。
    graph.add_conditional_edges(
        "planner_semantic_review_node",
        _route_after_planner,
        {
            "data_node": "data_node",
            "knowledge_node": "knowledge_node",
            "reviewer_node": "reviewer_node",
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

    # Reviewer emits evidence status; the deterministic router owns all retry edges.
    graph.add_edge("reviewer_node", "smart_router_node")
    graph.add_conditional_edges(
        "smart_router_node",
        _route_after_smart_router,
        {
            "data_node": "data_node",
            "knowledge_node": "knowledge_node",
            "planner_node": "planner_node",
            "end": END,
        },
    )
    graph.add_edge("planner_terminal_node", END)
    graph.add_edge("planning_failure_node", END)

    return graph


# 编译后的工作流（可直接调用）
workflow = build_workflow().compile()


def run_analysis(
    question: str,
    user_id: int,
    *,
    company_id: int | None = None,
    conversation_context: dict | None = None,
    planner_memory: list[dict] | None = None,
    document_ids: list[int] | None = None,
    business_data_source: BusinessDataSource | None = None,
    schema_catalog: dict | None = None,
    semantic_review_enabled: bool = True,
    stage_callback: Callable[[str], None] | None = None,
    checkpoint_callback: Callable[[str, str | None, dict], None] | None = None,
    resume_next_node: str | None = None,
    resume_state: dict | None = None,
    tool_runtime: ToolRuntime | None = None,
) -> dict:
    """运行一次完整分析"""
    initial_state: WorkflowState = {
        "question": question,
        "user_id": user_id,
        "company_id": company_id,
        "plan": None,
        "planner_result": None,
        "planner_failure": None,
        "planner_outcome": None,
        "semantic_review_outcome": None,
        "data_result": None,
        "confirmed_facts": None,
        "knowledge_result": None,
        "data_outcome": None,
        "knowledge_outcome": None,
        "review_result": None,
        "reviewer_outcome": None,
        "terminal_result": None,
        "final_answer": None,
        "error": None,
        "conversation_context": conversation_context,
        "planner_memory": planner_memory or [],
        "document_ids": document_ids,
        "business_data_source": business_data_source,
        "schema_catalog": schema_catalog,
        "semantic_review_enabled": semantic_review_enabled,
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
        "tool_runtime": tool_runtime,
        "stage_callback": stage_callback,
        "checkpoint_callback": checkpoint_callback,
        "resume_next_node": resume_next_node,
    }
    # The persisted patch is selected by the Worker, not supplied by a client.
    # Keep this allow-list tight so a stale/old checkpoint cannot replace scope.
    for key in (
        "plan",
        "planner_result",
        "planner_failure",
        "planner_outcome",
        "semantic_review_outcome",
        "data_result",
        "confirmed_facts",
        "knowledge_result",
        "data_outcome",
        "knowledge_outcome",
        "review_result",
        "reviewer_outcome",
        "terminal_result",
        "final_answer",
        "error",
        "scope_fingerprint",
        "external_retry_count",
        "routing_action",
        "routing_feedback",
        "loop_stop_reason",
        "loop_history",
        "cached_data_result",
        "cached_knowledge_result",
        "cache_scope_fingerprint",
        "empty_result_replanned",
    ):
        if isinstance(resume_state, dict) and key in resume_state:
            initial_state[key] = resume_state[key]
    return workflow.invoke(initial_state)
