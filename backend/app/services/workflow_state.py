"""LangGraph 工作流状态定义"""

from collections.abc import Callable
from typing import TypedDict

from typing_extensions import NotRequired

from app.models.company import BusinessDataSource


class WorkflowState(TypedDict):
    """在所有节点间共享的状态"""

    question: str  # 用户问题
    user_id: int  # 用户ID
    company_id: int | None  # Worker 从已持久化任务读取的公司范围
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
    document_ids: list[int] | None
    business_data_source: BusinessDataSource | None
    schema_catalog: dict | None
    semantic_review_enabled: bool
    scope_fingerprint: str | None
    external_retry_count: int
    max_external_retries: int
    routing_action: str | None
    routing_feedback: dict | None
    loop_stop_reason: str | None
    loop_history: list[dict]
    cached_data_result: dict | None
    cached_knowledge_result: dict | None
    cache_scope_fingerprint: str | None
    empty_result_replanned: bool
    stage_callback: NotRequired[Callable[[str], None]]
