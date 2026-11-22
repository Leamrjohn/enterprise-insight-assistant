"""What the conversation summarizer may see (C9).

The summarizer merges the messages that just left the context window into the
summary so far.  Neither may be left out: a summary built without the old items
would lose them, and one without the new messages has nothing to add.  Older
assistant replies shrink first; a batch that still cannot fit is refused, and
the summary then stays as it was.

Raise the version whenever a section, field or number here changes.
"""

from app.modules.runtime.context.compressors import compress_history
from app.modules.runtime.context.engine import ContextPolicy, SectionRule

SUMMARY = ContextPolicy(
    node="summary",
    version="summary/1",
    budget_tokens=4000,
    # Eight items of at most 120 characters each.
    output_reserve_tokens=1024,
    sections={
        # First entries give way first.
        "history": SectionRule(
            fields=("messages",), compress=compress_history, required=True
        ),
        "system": SectionRule(required=True),
        "current_summary": SectionRule(required=True),
    },
    on_over_budget="reject",
)
# Calls a task may spend on its summary, outside its max_calls.
SUMMARY_MAX_CALLS = 1
