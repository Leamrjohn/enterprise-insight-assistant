"""How a Planner proposal becomes the next conversation state (C6b).

The model only proposes; code checks every item against the user's own words
before it changes the state.  Pure functions, no database.
"""

from __future__ import annotations

import copy
from collections.abc import Iterable
from typing import Protocol

# The dimensions a standing constraint may set.  There is no "company" or
# "data source" dimension on purpose: scope and permission are never state.
DIMENSIONS = frozenset(
    {
        "region",
        "customer_tier",
        "order_status",
        "period",
        "product_category",
        "complaint_severity",
    }
)
# include: only this value; exclude: everything but this value; clear: the user
# withdrew the constraint on this dimension.
OPS = frozenset({"include", "exclude", "clear"})
MAX_QUOTE_CHARS = 200

# Why an item was dropped; kept with its index so shadow mode can report it.
UNKNOWN_DIMENSION = "unknown_dimension"
UNKNOWN_OP = "unknown_op"
NOT_USER_MESSAGE = "not_user_message"
QUOTE_NOT_IN_MESSAGE = "quote_not_in_message"
QUOTE_TOO_LONG = "quote_too_long"
VALUE_NOT_IN_QUOTE = "value_not_in_quote"


class Message(Protocol):
    id: int
    role: str
    content: str | None


def apply_update(
    state: dict, updates: list[dict], messages: Iterable[Message]
) -> tuple[dict, list[dict]]:
    """Return (new state, rejected items); ``state`` itself is never changed.

    Each update is ``{"dimension", "op", "value", "source_message_id",
    "quote"}``.  It is applied only if all of these hold, checked in this
    order, and the first that fails is the reason it is rejected:
    1. ``dimension`` is in DIMENSIONS              else UNKNOWN_DIMENSION
    2. ``op`` is in OPS                            else UNKNOWN_OP
    3. ``source_message_id`` is a *user* message   else NOT_USER_MESSAGE
    4. ``quote`` is non-empty and appears verbatim
       in that message's content                   else QUOTE_NOT_IN_MESSAGE
    5. ``quote`` has at most MAX_QUOTE_CHARS       else QUOTE_TOO_LONG
    6. for include / exclude: ``value`` is non-empty
       and appears verbatim in ``quote``           else VALUE_NOT_IN_QUOTE

    An accepted include / exclude replaces whatever that dimension held, as
    ``{"op", "value", "source_message_id", "quote"}`` under
    ``state["constraints"][dimension]``; an accepted clear removes the
    dimension (nothing to remove is fine).  Updates apply in list order, so a
    later one on the same dimension wins.  A rejected item is reported as
    ``{"index": <its position in updates>, "reason": <code>}`` and the other
    items still apply.
    """
    new_state = copy.deepcopy(state)
    by_id = {message.id: message for message in messages}
    rejected: list[dict] = []
    for index, update in enumerate(updates):
        dimension, op = update.get("dimension"), update.get("op")
        quote, value = update.get("quote") or "", update.get("value")
        source_id = update.get("source_message_id")
        source = by_id.get(source_id) if isinstance(source_id, int) else None
        if dimension not in DIMENSIONS:
            reason = UNKNOWN_DIMENSION
        elif op not in OPS:
            reason = UNKNOWN_OP
        elif source is None or source.role != "user":
            reason = NOT_USER_MESSAGE
        elif not quote or quote not in (source.content or ""):
            reason = QUOTE_NOT_IN_MESSAGE
        elif len(quote) > MAX_QUOTE_CHARS:
            reason = QUOTE_TOO_LONG
        elif op != "clear" and (not value or value not in quote):
            reason = VALUE_NOT_IN_QUOTE
        else:
            reason = None
        if reason is not None:
            rejected.append({"index": index, "reason": reason})
            continue
        if op == "clear":
            new_state["constraints"].pop(dimension, None)
        else:
            new_state["constraints"][dimension] = {
                "op": op,
                "value": value,
                "source_message_id": source_id,
                "quote": quote,
            }
    return new_state, rejected


def set_subject(state: dict, entities: list[str], period: str | None) -> dict:
    """The subject the next "this region" refers to: the last analysis's scope."""
    new_state = {**state, "subject": {"entities": list(entities), "period": period}}
    return new_state
