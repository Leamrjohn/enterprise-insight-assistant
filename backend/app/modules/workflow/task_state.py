"""The only allowed AnalysisTask status transitions."""

TASK_TRANSITIONS: dict[str, frozenset[str]] = {
    "queued": frozenset({"running", "cancelled"}),
    "retrying": frozenset({"running", "cancelled"}),
    "running": frozenset(
        {
            "retrying",
            "awaiting_review",
            "completed",
            "partial",
            "failed",
            "cancelled",
            "needs_clarification",
        }
    ),
    "awaiting_review": frozenset({"queued", "partial"}),
    "completed": frozenset(),
    "partial": frozenset(),
    "failed": frozenset(),
    "cancelled": frozenset(),
    "needs_clarification": frozenset(),
}


def require_task_transition(current: str, target: str) -> None:
    if target not in TASK_TRANSITIONS.get(current, frozenset()):
        raise ValueError(f"invalid analysis task transition: {current} -> {target}")
