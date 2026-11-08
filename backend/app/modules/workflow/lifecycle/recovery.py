"""Explicit recovery decisions for retrying a workflow node safely."""

from typing import Literal

from pydantic import BaseModel

RecoveryMode = Literal["retry_node", "rerun_downstream"]


class RecoveryDecision(BaseModel):
    """Describe the smallest safe replay boundary after a retryable failure."""

    mode: RecoveryMode
    resume_node: str
    invalidated_state_keys: list[str]


_DECISIONS = {
    "planner_node": RecoveryDecision(
        mode="rerun_downstream",
        resume_node="planner_node",
        invalidated_state_keys=[
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
        ],
    ),
    "planner_semantic_review_node": RecoveryDecision(
        mode="rerun_downstream",
        resume_node="planner_semantic_review_node",
        invalidated_state_keys=[
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
        ],
    ),
    "data_node": RecoveryDecision(
        mode="rerun_downstream",
        resume_node="data_node",
        invalidated_state_keys=[
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
        ],
    ),
    "knowledge_node": RecoveryDecision(
        mode="rerun_downstream",
        resume_node="knowledge_node",
        invalidated_state_keys=[
            "knowledge_result",
            "knowledge_outcome",
            "review_result",
            "reviewer_outcome",
            "terminal_result",
            "final_answer",
            "error",
        ],
    ),
    "reviewer_node": RecoveryDecision(
        mode="retry_node",
        resume_node="reviewer_node",
        invalidated_state_keys=[
            "review_result",
            "reviewer_outcome",
            "terminal_result",
            "final_answer",
            "error",
        ],
    ),
}


def recovery_decision_for_node(node_name: str) -> RecoveryDecision | None:
    """Return an allow-listed recovery policy; never infer graph topology at runtime."""
    return _DECISIONS.get(node_name)


def apply_recovery_decision(state: dict, decision: RecoveryDecision) -> dict:
    """Remove all invalid outputs before a graph resumes from the selected node."""
    resumed = dict(state)
    for key in decision.invalidated_state_keys:
        resumed.pop(key, None)
    resumed["recovery_decision"] = decision.model_dump(mode="json")
    return resumed
