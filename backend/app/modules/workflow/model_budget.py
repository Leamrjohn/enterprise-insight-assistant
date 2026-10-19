"""Server-owned, task-frozen model budget policy."""

from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.settings import Settings


def configured_model_budget(settings: "Settings") -> dict[str, int | str]:
    """Build the JSON-safe budget copied into every newly created task.

    The client never supplies these values.  Persisting the complete policy at
    creation prevents later settings edits from loosening an already admitted
    task's limits.
    """
    maximum_cost = Decimal(settings.analysis_task_model_max_cost)
    return {
        "max_calls": settings.analysis_task_model_max_calls,
        "max_calls_per_node": settings.analysis_task_model_max_calls_per_node,
        "max_repairs": settings.analysis_task_model_max_repairs,
        "max_total_tokens": settings.analysis_task_model_max_total_tokens,
        "max_cost": format(maximum_cost, "f"),
    }
