"""Decide which proposed summary items are kept (C9).

The summarizer model only proposes items; code checks that every item cites
real messages that have left the context window, the same way
``state_update.apply_update`` checks a state proposal.
"""

from __future__ import annotations

import copy
from collections.abc import Iterable, Sequence

from app.modules.conversations.state_update import Message
from app.modules.conversations.summary import MAX_SUMMARY_ITEMS

MAX_ITEM_CHARS = 120

BAD_TEXT = "bad_text"
NO_SOURCE = "no_source"
UNKNOWN_MESSAGE = "unknown_message"
MESSAGE_IN_WINDOW = "message_in_window"
OVER_ITEM_LIMIT = "over_item_limit"


def apply_summary(
    summary: dict,
    items: list[dict],
    messages: Iterable[Message],
    *,
    window_start_id: int,
) -> tuple[dict, list[dict]]:
    """Return (new summary, rejected items); ``summary`` itself is never changed.

    ``items`` is the summarizer's full new list; the kept ones replace the old
    items.  ``messages`` are the conversation's messages, and
    ``window_start_id`` is the oldest message still in the context window, so
    only ids below it may be cited.  A rejected item is reported as
    ``{"index": <its position in items>, "reason": <code>}``; once
    MAX_SUMMARY_ITEMS are kept, the rest are rejected as OVER_ITEM_LIMIT.
    ``covered_through`` becomes the newest message outside the window.
    """
    new_summary = copy.deepcopy(summary)
    by_id = {message.id: message for message in messages}
    kept: list[dict] = []
    rejected: list[dict] = []
    for index, item in enumerate(items):
        reason = _reject_reason(item, by_id, window_start_id)
        if reason is None and len(kept) >= MAX_SUMMARY_ITEMS:
            reason = OVER_ITEM_LIMIT
        if reason is not None:
            rejected.append({"index": index, "reason": reason})
            continue
        kept.append(
            {
                "text": item["text"].strip(),
                "source_message_ids": sorted(set(item["source_message_ids"])),
            }
        )
    new_summary["items"] = kept
    outside = [message_id for message_id in by_id if message_id < window_start_id]
    new_summary["covered_through"] = max(
        outside, default=summary.get("covered_through", 0)
    )
    return new_summary, rejected


def _reject_reason(
    item: dict, by_id: dict[int, Message], window_start_id: int
) -> str | None:
    """The first check ``item`` fails, or None when it may be kept.

    Checked in this order:
    1. ``text`` is a string that is not blank after strip(),
       with at most MAX_ITEM_CHARS characters          else BAD_TEXT
    2. ``source_message_ids`` is a non-empty list whose
       every element is an int (a bool is not an int)  else NO_SOURCE
    3. every id is a key of ``by_id``                  else UNKNOWN_MESSAGE
    4. every id is below ``window_start_id``           else MESSAGE_IN_WINDOW
    """
    text = item.get("text")
    source_message_ids = item.get("source_message_ids")
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_ITEM_CHARS:
        return BAD_TEXT
    if (
        not isinstance(source_message_ids, list)
        or not source_message_ids
        or not all(
            isinstance(message_id, int) and not isinstance(message_id, bool)
            for message_id in source_message_ids
        )
    ):
        return NO_SOURCE
    if not all(message_id in by_id for message_id in source_message_ids):
        return UNKNOWN_MESSAGE
    if not all(message_id < window_start_id for message_id in source_message_ids):
        return MESSAGE_IN_WINDOW
    return None


def window_start(messages: Sequence[Message], *, window_size: int) -> int | None:
    """The id of the oldest message the next task still sees, or None.

    The next task sees the last ``window_size`` messages with content (blank
    or None content is skipped, as the conversation context does).  None
    means no message has left the window yet.  ``messages`` are in id order.
    """
    with_content = []
    for m in messages:
        if not (m.content or "").strip():
            continue
        with_content.append(m)
    if len(with_content) <= window_size:
        return None
    else:
        return with_content[-window_size].id


def messages_to_summarize(
    messages: Sequence[Message],
    *,
    covered_through: int,
    window_start_id: int,
    limit: int,
) -> list[Message]:
    """The oldest ``limit`` messages with content that are newer than
    ``covered_through`` and older than ``window_start_id``, in id order."""
    partil_messages = [
        m
        for m in messages
        if covered_through < m.id < window_start_id and (m.content or "").strip()
    ]
    return partil_messages[:limit]
