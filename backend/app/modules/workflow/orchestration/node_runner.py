"""B1b: one wrapper for what every node used to do by hand.

Order is fixed: cancellation check -> skip check -> stage -> node -> checkpoint.
"""

import functools
from collections.abc import Callable
from dataclasses import dataclass

from app.modules.runtime.model_governance import ModelCallCancelled
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


@dataclass(frozen=True)
class NodeStep:
    """A node's update plus where a resumed task should continue."""

    next_node: str | None
    update: dict


NodeFn = Callable[[WorkflowState], "NodeStep | dict"]


def run_node(
    name: str,
    stage: str | None,
    fn: NodeFn,
    *,
    skip_if: Callable[[WorkflowState], bool] | None = None,
) -> Callable[[WorkflowState], dict]:
    """Wrap ``fn`` as a graph node.

    ``stage=None`` means the node shows no stage of its own.  ``skip_if`` lets a
    switched-off node return ``{}`` before any stage or checkpoint is written.
    Only a ``NodeStep`` result is checkpointed; a plain dict is returned as is.
    """

    @functools.wraps(fn)
    def node(state: WorkflowState) -> dict:
        cancel_check = state.get("cancel_check")
        if cancel_check is not None and cancel_check():
            raise ModelCallCancelled("task cancelled")
        if skip_if is not None and skip_if(state):
            return {}
        if stage is not None:
            _set_stage(state, stage, name)
        result = fn(state)
        if isinstance(result, NodeStep):
            return _checkpoint(
                state,
                completed_node=name,
                next_node=result.next_node,
                update=result.update,
            )
        return result

    node.__name__ = name
    node.__qualname__ = name
    return node
