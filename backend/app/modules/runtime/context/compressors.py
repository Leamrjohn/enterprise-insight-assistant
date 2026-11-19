"""Section compressors (C4): code only, so nothing is reworded.

Each takes one section's value and returns a shorter one, or the same value
when there is nothing to shorten.  The engine compares the two to decide
whether the section counts as compressed.
"""

from __future__ import annotations

from typing import Any

# Earlier turns kept when the Planner's history has to shrink.
HISTORY_KEEP_MESSAGES = 4


def compress_history(conversation_context: Any) -> Any:
    """Keep the latest messages and say that earlier ones were left out.

    standing_constraints stay whole: they exist because old turns get cut.
    """
    if not isinstance(conversation_context, dict):
        return conversation_context
    messages = conversation_context.get("messages") or []
    if len(messages) <= HISTORY_KEEP_MESSAGES:
        return conversation_context
    else:
        shrunk = {
            **conversation_context,
            "history_truncated": True,
            "messages": messages[-HISTORY_KEEP_MESSAGES:],
        }
        return shrunk
