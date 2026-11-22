"""What the conversation state extractor may see (C6f).

The extractor judges the current user message against the constraints already
in force; the recent messages only help it resolve words like "this region".
Older assistant replies shrink first, and the history may be left out whole:
the current message alone still lets it record a scope.  A current message that
cannot fit is refused, and the extractor then proposes nothing.

There is no shadow mode: the node is new, so there is no older prompt to keep.

Raise the version whenever a section, field or number here changes.
"""

from app.modules.runtime.context.compressors import compress_history
from app.modules.runtime.context.engine import ContextPolicy, SectionRule

STATE_EXTRACT = ContextPolicy(
    node="state_extract",
    version="state_extract/1",
    budget_tokens=3000,
    output_reserve_tokens=256,
    sections={
        # First entries give way first.
        "history": SectionRule(
            fields=("messages",), compress=compress_history, droppable=True
        ),
        "system": SectionRule(required=True),
        "current_state": SectionRule(required=True),
        "current_message": SectionRule(required=True),
    },
    on_over_budget="reject",
)
# Calls a task may spend on extraction, outside its max_calls (M7c).
STATE_EXTRACT_MAX_CALLS = 1
