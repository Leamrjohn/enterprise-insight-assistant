"""LangGraph 工作流状态定义"""

from typing import TypedDict


class WorkflowState(TypedDict):
    """在所有节点间共享的状态"""

    question: str  # 用户问题
    user_id: int  # 用户ID
    plan: dict | None  # Planner生成的计划
    planner_result: dict | None  # Planner 实际模型调用次数与状态
    planner_failure: dict | None  # Planner 调用或结构化校验失败信息
    data_result: dict | None  # DataAgent返回的结果
    knowledge_result: dict | None  # KnowledgeAgent返回的结果
    review_result: dict | None  # ReviewerAgent返回的结果
    terminal_result: dict | None  # 无需业务 Agent 或规划失败时的终态信息
    final_answer: str | None  # 最终回答
    error: str | None  # 错误信息
    conversation_context: dict | None
