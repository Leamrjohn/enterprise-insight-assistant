"""LangGraph 工作流图 —— 把 Agent 节点串成可执行的工作流"""

from typing import Literal

from langgraph.graph import StateGraph, START, END

from app.services.workflow_state import WorkflowState
from app.services.workflow_nodes import (
    planner_node,
    knowledge_node,
    data_node,
    reviewer_node,
)


def _need_data(state: WorkflowState) -> Literal["data_node", "knowledge_node"]:
    """条件分支：是否需要先查数据？"""
    plan = state.get("plan") or {}
    return "data_node" if plan.get("need_data") else "knowledge_node"


def _need_knowledge(state: WorkflowState) -> Literal["knowledge_node", "reviewer_node"]:
    """条件分支：是否需要查文档？"""
    plan = state.get("plan") or {}
    return "knowledge_node" if plan.get("need_knowledge") else "reviewer_node"


def build_workflow() -> StateGraph:
    """
    构建工作流图：

    START
      → planner_node ──条件──→ data_node ──→ knowledge_node
                                  └──→ knowledge_node ──→ reviewer_node
                                                              └──→ END
    """
    graph = StateGraph(WorkflowState)

    # 注册所有节点
    graph.add_node("planner_node", planner_node)
    graph.add_node("data_node", data_node)
    graph.add_node("knowledge_node", knowledge_node)
    graph.add_node("reviewer_node", reviewer_node)

    # 边：START → planner
    graph.add_edge(START, "planner_node")

    # 条件边：planner → data 或 knowledge
    graph.add_conditional_edges("planner_node", _need_data, {
        "data_node": "data_node",
        "knowledge_node": "knowledge_node",
    })

    # 条件边：data → knowledge（data查完后必须再查knowledge）
    graph.add_conditional_edges("data_node", _need_knowledge, {
        "knowledge_node": "knowledge_node",
        "reviewer_node": "reviewer_node",
    })

    # 边：knowledge → reviewer
    graph.add_edge("knowledge_node", "reviewer_node")

    # 边：reviewer → END
    graph.add_edge("reviewer_node", END)

    return graph


# 编译后的工作流（可直接调用）
workflow = build_workflow().compile()


def run_analysis(question: str, user_id: int) -> dict:
    """运行一次完整分析"""
    initial_state: WorkflowState = {
        "question": question,
        "user_id": user_id,
        "plan": None,
        "data_result": None,
        "knowledge_result": None,
        "review_result": None,
        "final_answer": None,
        "error": None,
    }
    return workflow.invoke(initial_state)
