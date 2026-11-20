"""Section compressors (C4): code only, so nothing is reworded.

Each takes one section's value and returns a shorter one, or the same value
when there is nothing to shorten.  The engine compares the two to decide
whether the section counts as compressed.
"""

from __future__ import annotations

from typing import Any

# The latest exchange is always sent whole.
HISTORY_RECENT_MESSAGES = 2
# Older assistant replies are cut to this many characters.
ASSISTANT_REPLY_CHARS = 80


def compress_history(conversation_context: Any) -> Any:
    """Shorten older assistant replies; never drop or cut what the user said.

    A user's scope ("only East China from now on") can sit in any turn the
    conversation service selected, and only some of those reach
    standing_constraints, so dropping turns could lose one silently.  If the
    history still does not fit, the Planner asks back instead (clarify).
    """
    if not isinstance(conversation_context, dict):
        return conversation_context
    messages = conversation_context.get("messages") or []
    older = messages[:-HISTORY_RECENT_MESSAGES]
    if not any(_is_long_reply(m) for m in older):
        return conversation_context
    shortened = [
        {
            **m,
            "content": m["content"][:ASSISTANT_REPLY_CHARS],
            "content_truncated": True,
        }
        if _is_long_reply(m)
        else m
        for m in older
    ]
    return {
        **conversation_context,
        "messages": [*shortened, *messages[-HISTORY_RECENT_MESSAGES:]],
        "history_truncated": True,
    }


def _is_long_reply(message: dict) -> bool:
    return (
        message.get("role") == "assistant"
        and len(message.get("content", "")) > ASSISTANT_REPLY_CHARS
    )
