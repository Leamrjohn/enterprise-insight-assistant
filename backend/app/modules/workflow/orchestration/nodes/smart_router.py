"""智能路由节点。"""

from app.modules.workflow.lifecycle.recovery import recovery_decision_for_node
from app.modules.workflow.orchestration.node_runner import NodeStep, run_node
from app.modules.workflow.orchestration.router import (
    MAX_EXTERNAL_RETRIES,
    build_feedback,
    choose_next_action,
)
from app.modules.workflow.orchestration.state import WorkflowState


def _smart_router_node(state: WorkflowState) -> NodeStep:
    """Bounded policy engine: choose a node from typed execution state only."""
    action, reason = choose_next_action(state)
    retries = state.get("external_retry_count", 0)
    maximum = state.get("max_external_retries", MAX_EXTERNAL_RETRIES)
    if action != "stop" and retries >= maximum:
        action, reason = "stop", "external_retry_budget_exhausted"

    history = [
        *(state.get("loop_history") or []),
        {
            "attempt": retries,
            "action": action,
            "reason": reason,
            "data_status": (state.get("data_result") or {}).get("status"),
            "knowledge_status": (state.get("knowledge_result") or {}).get("status"),
        },
    ]
    if action == "stop":
        existing_terminal = state.get("terminal_result") or {}
        outcome = existing_terminal.get("outcome") or (
            "insufficient_evidence"
            if reason
            in {
                "knowledge_insufficient",
                "evidence_exhausted",
                "data_insufficient",
                "no_matching_records",
            }
            else "failed"
            if reason == "non_retryable_or_unknown_failure"
            or reason.endswith("_denied")
            else "completed"
        )
        return NodeStep(
            next_node=None,
            update={
                "routing_action": action,
                "loop_stop_reason": reason,
                "loop_history": history,
                "terminal_result": {
                    **existing_terminal,
                    "outcome": outcome,
                    "reason": existing_terminal.get("reason", reason),
                },
            },
        )

    feedback = build_feedback(state, action, reason)
    failed_node = {
        "retry_data": "data_node",
        "retry_knowledge": "knowledge_node",
        "retry_reviewer": "reviewer_node",
        "replan": "planner_node",
    }[action]
    outcome_key = {
        "retry_data": "data_outcome",
        "retry_knowledge": "knowledge_outcome",
        "retry_reviewer": "reviewer_outcome",
        "replan": "planner_outcome",
    }[action]
    outcome = state.get(outcome_key)
    error_code = (
        feedback.get("error_code")
        if isinstance(feedback, dict) and feedback.get("error_code")
        else outcome.get("error_code")
        if isinstance(outcome, dict) and outcome.get("error_code")
        else reason
    )
    decision = recovery_decision_for_node(failed_node)
    assert decision is not None
    updates = {
        "routing_action": action,
        "routing_feedback": feedback,
        "recovery_decision": decision.model_dump(mode="json"),
        "retry_context": {
            "failed_node": failed_node,
            "error_code": error_code,
            "retry_number": retries + 1,
            "recovery_mode": decision.mode,
        },
        "external_retry_count": retries + 1,
        "loop_history": history,
    }
    updates.update({key: None for key in decision.invalidated_state_keys})
    if action == "replan":
        updates["empty_result_replanned"] = state.get("empty_result_replanned") or (
            reason == "empty_result_scope_check"
        )
    return NodeStep(
        next_node=decision.resume_node,
        update=updates,
    )


smart_router_node = run_node(
    "smart_router_node", "composing_report", _smart_router_node
)
