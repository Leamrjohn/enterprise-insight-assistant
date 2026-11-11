"""C2: measure what every model call carries, without changing any call.

Goal: for each model call, count the tokens of each prompt section (system,
question, history, schema, evidence ...) so we get per-node P50/P95/max after a
smoke round.  Recording must never change what is sent, and never store text:
only section names and token counts.

Flow (option A, step 2): a call site runs ``declare_sections(...)`` right
before ``gateway.chat``; ``reserve_model_call`` (model_governance) takes the
declaration and stores ``context_usage(...)`` in that call's
``model_call_records.resource_usage["context_tokens"]``.  The record already
has node_name, prompt_tokens and model_call_id, so the baseline is one query.
"""

from __future__ import annotations

from collections.abc import Mapping
from contextvars import ContextVar
from typing import Any

from app.core.tokenizer import count_tokens

_declared: ContextVar[dict[str, str] | None] = ContextVar(
    "declared_context_sections", default=None
)


def declare_sections(**sections: str) -> None:
    """Call right before one model call: each prompt part's name and text."""
    _declared.set(dict(sections))


def take_declared_sections() -> dict[str, str] | None:
    """The sections declared for the call being made, then forget them.

    Clearing matters: a retry or the next node must not reuse an old
    declaration.  Returns None when the call site declared nothing.
    """
    sections = _declared.get()
    _declared.set(None)
    return sections


def context_usage(sections: Mapping[str, str] | None) -> dict[str, Any]:
    """What reserve_model_call stores under resource_usage["context_tokens"].

    Declared:  {"declared": True, "tokens": measure_sections(sections)}
    None:      {"declared": False}   (call site not wired yet; still visible)
    No text from the sections, ever.
    """
    if sections is None:
        return {"declared": False}
    return {"declared": True, "tokens": measure_sections(sections)}


def measure_sections(sections: Mapping[str, str]) -> dict[str, int]:
    """Token count per section name, plus "total" for the sum.

    Example: {"system": "你好", "question": "abc"} ->
             {"system": 1, "question": 1, "total": 2}
    Empty sections count 0.  Section text is never returned.
    """
    result = {}
    for key, value in sections.items():
        tokens = count_tokens(value)
        result[key] = tokens
    result["total"] = sum(result.values())
    return result


def measurement_details(node: str, sections: Mapping[str, str]) -> dict[str, Any]:
    """The ``details`` payload for append_workflow_event(event_type="context_measured").

    Shape: {"node": node, "tokens": measure_sections(sections)}
    It must contain no text from the sections (the tests check this).
    """
    return {"node": node, "tokens": measure_sections(sections)}
