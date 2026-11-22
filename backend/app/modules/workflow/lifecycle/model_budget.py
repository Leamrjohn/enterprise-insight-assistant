"""Server-owned, task-frozen model budget policy."""

from decimal import Decimal
from typing import TYPE_CHECKING

from app.modules.runtime.context.policies.state_extract import (
    STATE_EXTRACT,
    STATE_EXTRACT_MAX_CALLS,
)

if TYPE_CHECKING:
    from app.core.settings import Settings


def configured_model_budget(
    settings: "Settings", *, state_extract: bool = False
) -> dict[str, int | str]:
    """Build the JSON-safe budget copied into every newly created task.

    The client never supplies these values.  Persisting the complete policy at
    creation prevents later settings edits from loosening an already admitted
    task's limits.
    """
    maximum_cost = Decimal(settings.analysis_task_model_max_cost)
    budget: dict[str, int | str] = {
        "max_calls": settings.analysis_task_model_max_calls,
        "max_calls_per_node": settings.analysis_task_model_max_calls_per_node,
        "max_repairs": settings.analysis_task_model_max_repairs,
        "max_total_tokens": settings.analysis_task_model_max_total_tokens,
        "max_cost": format(maximum_cost, "f"),
    }
    if state_extract:
        # M7c: a task that froze a conversation state gets one extraction call
        # of its own, so the answer path keeps all of max_calls.  Its tokens
        # are added on top; the cost limit stays the one safety ceiling.
        budget["state_extract_max_calls"] = STATE_EXTRACT_MAX_CALLS
        budget["max_total_tokens"] = (
            settings.analysis_task_model_max_total_tokens
            + STATE_EXTRACT.budget_tokens
            + settings.llm_max_output_tokens
        )
    return budget
