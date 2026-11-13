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

Fallback (step 3): a call site that declared nothing is still split, coarsely,
by the gateway: ``gateway_sections(...)`` cuts the request into what the
gateway can see (system / prompt, or the tool-loop messages by role plus the
tool schemas) and the record says ``"declared": "auto"``.
"""

from __future__ import annotations

import json
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


def context_usage(
    sections: Mapping[str, str] | None,
    fallback: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """What reserve_model_call stores under resource_usage["context_tokens"].

    Declared:  {"declared": True, "tokens": measure_sections(sections)}
    Fallback:  {"declared": "auto", "tokens": measure_sections(fallback)}
               (call site declared nothing; the gateway split it)
    Neither:   {"declared": False}   (still visible)
    A declaration always wins over the fallback.  No text, ever.
    """
    if sections is not None:
        return {"declared": True, "tokens": measure_sections(sections)}
    if fallback is not None:
        return {"declared": "auto", "tokens": measure_sections(fallback)}
    return {"declared": False}


def gateway_sections(
    prompt: str,
    system_prompt: str | None = None,
    messages: list[dict] | None = None,
    tools: list[dict] | None = None,
) -> dict[str, str]:
    """The sections a gateway can see in one request (C2 fallback)."""
    if messages is None:
        return {"system": system_prompt or "", "prompt": prompt}
    else:
        result = {
            "system": "",
            "user": "",
            "assistant": "",
            "tool_results": "",
            "tools": "",
        }
        roles = {
            "system": "system",
            "user": "user",
            "assistant": "assistant",
            "tool": "tool_results",
        }
        for msg in messages:
            k = roles.get(msg["role"], msg["role"])
            if k in result and msg.get("content"):
                result[k] += ("\n" if result[k] else "") + msg["content"]
            if k in result and msg.get("tool_calls"):
                result[k] += ("\n" if result[k] else "") + json.dumps(
                    msg["tool_calls"], ensure_ascii=False
                )
        result["tools"] = (
            json.dumps(tools, ensure_ascii=False) if tools is not None else ""
        )
        return result


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
