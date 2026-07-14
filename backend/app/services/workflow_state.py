"""LangGraph 工作流状态定义"""

from typing import TypedDict


class WorkflowState(TypedDict):
    """在所有节点间共享的状态"""
    question: str              # 用户问题
    user_id: int               # 用户ID
    plan: dict | None          # Planner生成的计划
    data_result: dict | None   # DataAgent返回的结果
    knowledge_result: dict | None  # KnowledgeAgent返回的结果
    review_result: dict | None # ReviewerAgent返回的结果
    final_answer: str | None   # 最终回答
    error: str | None          # 错误信息
