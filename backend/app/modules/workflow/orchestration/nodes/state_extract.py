"""M7 状态抽取节点。"""

from dataclasses import dataclass

from app.core.gateway.factory import get_model_gateway
from app.modules.conversations.state import STATE_SNAPSHOT_KEY
from app.modules.conversations.state_extractor import extract_state_update
from app.modules.conversations.state_update import apply_update
from app.modules.runtime.context.policies.state_extract import STATE_EXTRACT
from app.modules.runtime.model_governance import model_node_scope
from app.modules.workflow.orchestration.nodes._common import (
    _checkpoint,
    _set_stage,
)
from app.modules.workflow.orchestration.state import WorkflowState


@dataclass
class _Message:
    """A snapshot message as conversations.state_update.Message."""

    id: int
    role: str
    content: str | None


def state_extract_node(state: WorkflowState) -> dict:
    """M7: check this message's state proposals before planning.

    Runs only when the API froze a state into the snapshot (mode shadow or
    enforce).  The model only proposes; apply_update keeps what the user's own
    words support.  A failed extraction keeps the frozen state, so planning
    never depends on it.
    """
    frozen = (state.get("conversation_context") or {}).get(STATE_SNAPSHOT_KEY)
    if not frozen:
        return {}
    _set_stage(state, "planning", "state_extract_node")
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
    return _checkpoint(
        state,
        completed_node="state_extract_node",
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
