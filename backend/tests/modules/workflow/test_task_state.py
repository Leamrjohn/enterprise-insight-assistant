import pytest
from app.modules.workflow.task_state import require_task_transition


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("queued", "running"),
        ("retrying", "running"),
        ("running", "partial"),
        ("running", "awaiting_review"),
        ("awaiting_review", "queued"),
        ("awaiting_review", "partial"),
    ],
)
def test_task_state_accepts_only_documented_legal_edges(
    current: str, target: str
) -> None:
    require_task_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("completed", "running"),
        ("awaiting_review", "completed"),
        ("partial", "queued"),
        ("needs_clarification", "completed"),
        ("unknown", "running"),
    ],
)
def test_task_state_rejects_illegal_edges(current: str, target: str) -> None:
    with pytest.raises(ValueError, match="invalid analysis task transition"):
        require_task_transition(current, target)
