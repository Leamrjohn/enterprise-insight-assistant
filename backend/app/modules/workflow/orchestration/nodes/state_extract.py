"""M7 状态抽取节点。"""

from dataclasses import dataclass

from app.core.gateway.factory import get_model_gateway
from app.modules.conversations.state import STATE_SNAPSHOT_KEY
from app.modules.conversations.state_extractor import extract_state_update
from app.modules.conversations.state_update import apply_update
from app.modules.runtime.context.policies.state_extract import STATE_EXTRACT
from app.modules.runtime.model_governance import model_node_scope
from app.modules.workflow.orchestration.node_runner import NodeStep, run_node
from app.modules.workflow.orchestration.state import WorkflowState


@dataclass
class _Message:
    """A snapshot message as conversations.state_update.Message."""

    id: int
    role: str
    content: str | None


def _state_extract_node(state: WorkflowState) -> NodeStep:
    """M7: check this message's state proposals before planning.

    Runs only when the API froze a state into the snapshot (mode shadow or
    enforce).  The model only proposes; apply_update keeps what the user's own
    words support.  A failed extraction keeps the frozen state, so planning
    never depends on it.
    """
    frozen = _frozen_state(state)
    history = [
        _Message(id=m["id"], role=m["role"], content=m["content"])
        for m in (state.get("conversation_context") or {}).get("messages", [])
    ]
    current = _Message(id=frozen["message_id"], role="user", content=state["question"])
    with model_node_scope(STATE_EXTRACT.node):
        extraction = extract_state_update(
            get_model_gateway(), state=frozen["state"], history=history, current=current
        )
    new_state, rejected = apply_update(
        frozen["state"], extraction.updates, [*history, current]
    )
    return NodeStep(
        next_node="planner_node",
        update={
            "conversation_state": new_state,
            "state_extraction": {
                "error": extraction.error,
                "proposed": len(extraction.updates),
                "rejected": rejected,
            },
        },
    )


def _frozen_state(state: WorkflowState) -> dict | None:
    return (state.get("conversation_context") or {}).get(STATE_SNAPSHOT_KEY)


def _no_frozen_state(state: WorkflowState) -> bool:
    return not _frozen_state(state)


state_extract_node = run_node(
    "state_extract_node", "planning", _state_extract_node, skip_if=_no_frozen_state
)
