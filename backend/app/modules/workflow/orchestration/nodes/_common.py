"""工作流节点共用的阶段、检查点和开关。"""

from app.core.config.snapshot import runtime_settings
from app.modules.workflow.orchestration.state import WorkflowState


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
