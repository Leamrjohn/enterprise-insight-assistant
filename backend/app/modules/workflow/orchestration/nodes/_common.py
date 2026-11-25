"""工作流节点共用的阶段、检查点和开关。"""

from app.core.config.snapshot import runtime_settings
from app.modules.workflow.orchestration.state import WorkflowState


def _set_stage(state: WorkflowState, stage: str, node_name: str) -> None:
    callback = state.get("stage_callback")
    if callback is not None:
        callback(stage, node_name)


def _checkpoint(
    state: WorkflowState,
    *,
    completed_node: str,
    next_node: str | None,
    update: dict,
) -> dict:
    """Persist a node's structured output after the node has completed."""
    callback = state.get("checkpoint_callback")
    if callback is not None:
        # Later nodes require earlier structured outputs too (for example,
        # Knowledge needs the already-approved Planner plan after Data was
        # completed).  Persist a small allow-listed cumulative snapshot rather
        # than the entire runtime state, which contains sessions and callbacks.
        snapshot_keys = (
            "conversation_state",
            "state_extraction",
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
            "retry_context",
            "recovery_decision",
            "loop_stop_reason",
            "loop_history",
            "empty_result_replanned",
        )
        snapshot = {
            key: update[key] if key in update else state.get(key)
            for key in snapshot_keys
            if (update[key] if key in update else state.get(key)) is not None
        }
        callback(completed_node, next_node, snapshot)
    return update


def _next_after_plan(plan: dict | None) -> str:
    if not isinstance(plan, dict):
        return "planning_failure_node"
    if plan.get("action") == "analyze":
        return (
            "data_node"
            if plan.get("route") in {"data_only", "hybrid"}
            else "knowledge_node"
        )
    return "planner_terminal_node"


def _effective_question(state: WorkflowState) -> str:
    """Use the Planner's standalone question without overwriting user input."""
    return (state.get("plan") or {}).get("resolved_question") or state["question"]


def model_tools_enabled(company_id: int | None) -> bool:
    """Off by default; the allowlist lets one company try it before anyone else."""
    settings = runtime_settings()
    if settings.model_tool_mode == "all":
        return True
    return (
        settings.model_tool_mode == "allowlist"
        and company_id in settings.model_tool_company_ids
    )
