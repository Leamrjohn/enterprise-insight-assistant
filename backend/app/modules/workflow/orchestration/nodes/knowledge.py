"""Knowledge 节点：检索文档证据。"""

from app.core.config.snapshot import runtime_settings
from app.modules.analysis.agent_protocol import AgentInput
from app.modules.analysis.tool_protocol import Tool
from app.modules.knowledge.agent import KnowledgeAgent
from app.modules.knowledge.tool import RAGTool
from app.modules.knowledge.tool_agent import ToolCallingKnowledgeAgent
from app.modules.runtime.model_governance import model_node_scope
from app.modules.runtime.tool_guard import (
    CircuitBreaker,
    FallbackTool,
    GuardedTool,
    redis_breaker_store,
)
from app.modules.workflow.orchestration.node_outcome import NodeOutcome
from app.modules.workflow.orchestration.nodes._common import (
    _checkpoint,
    _effective_question,
    _set_stage,
    model_tools_enabled,
)
from app.modules.workflow.orchestration.state import WorkflowState


def _guarded_rag_tool() -> Tool:
    store = redis_breaker_store()
    local = GuardedTool(
        RAGTool(degrade_on_rerank_failure=True),
        CircuitBreaker("rag_search:local", store),
    )
    if runtime_settings().knowledge_evidence_transport != "mcp_stdio":
        return local
    from app.modules.knowledge.mcp_adapter import McpEvidenceReadTool

    return FallbackTool(
        GuardedTool(
            McpEvidenceReadTool.stdio(), CircuitBreaker("rag_search:mcp", store)
        ),
        local,
    )


def knowledge_node(state: WorkflowState) -> dict:
    """
    Knowledge 节点：检索文档证据。

    “使用 resolved_question，否则回退原始问题”和 state["user_id"]，
    写 state["knowledge_result"]。
    """
    _set_stage(state, "retrieving_knowledge", "knowledge_node")
    runtime = state.get("tool_runtime")
    support_check = runtime_settings().knowledge_support_check_enabled
    if runtime and model_tools_enabled(state.get("company_id")):
        agent = ToolCallingKnowledgeAgent(
            rag_tool=runtime.wrap(_guarded_rag_tool()), support_check=support_check
        )
    else:
        rag_tool = RAGTool()
        if runtime_settings().knowledge_evidence_transport == "mcp_stdio":
            from app.modules.knowledge.mcp_adapter import McpEvidenceReadTool

            rag_tool = McpEvidenceReadTool.stdio()
        agent = (
            KnowledgeAgent(rag_tool=runtime.wrap(rag_tool), support_check=support_check)
            if runtime
            else KnowledgeAgent(support_check=support_check)
        )
    with model_node_scope("knowledge"):
        result = agent.run(
            AgentInput(
                question=_effective_question(state),
                user_id=state["user_id"],
                context={
                    "company_id": state.get("company_id"),
                    "confirmed_facts": state.get("confirmed_facts") or [],
                    **(
                        {"retry_context": state["retry_context"]}
                        if state.get("retry_context") is not None
                        else {}
                    ),
                    **(
                        {"document_ids": state["document_ids"]}
                        if state.get("document_ids") is not None
                        else {}
                    ),
                    **(
                        {"feedback": state["routing_feedback"]}
                        if state.get("routing_feedback") is not None
                        else {}
                    ),
                },
            )
        )
    if result.success:
        knowledge_result = {
            "status": ("ready" if result.evidence else "insufficient_evidence"),
            "answer": result.answer,
            "evidences": result.evidence,
        }
        if result.error_code is not None:
            knowledge_result["error_code"] = result.error_code
        if result.attempts:
            knowledge_result["attempts"] = result.attempts
        update = {
            "knowledge_result": knowledge_result,
            "knowledge_outcome": NodeOutcome(
                status=("succeeded" if result.evidence else "insufficient_evidence"),
                output=knowledge_result,
                error_code=result.error_code,
                checkpoint_patch={"stage": "retrieving_knowledge"},
            ).model_dump(),
        }
        return _checkpoint(
            state,
            completed_node="knowledge_node",
            next_node="reviewer_node",
            update=update,
        )
    error_code = result.error_code or "knowledge_retrieval_failed"
    outcome_status = (
        "retryable_error" if error_code == "knowledge_retrieval_failed" else "denied"
    )
    update = {
        "knowledge_result": {
            "status": "failed",
            "error": result.error or "文档检索失败",
            "error_code": error_code,
        },
        "knowledge_outcome": NodeOutcome(
            status=outcome_status,
            output={},
            error_code=error_code,
            retry_hint="retry" if outcome_status == "retryable_error" else "stop",
            checkpoint_patch={"stage": "retrieving_knowledge"},
        ).model_dump(),
        "error": result.error,
    }
    return _checkpoint(
        state,
        completed_node="knowledge_node",
        next_node="reviewer_node",
        update=update,
    )
