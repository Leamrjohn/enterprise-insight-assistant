"""Ask the model which standing scope the current user message sets (C6f).

The extractor only proposes.  apply_update keeps the last word: a proposal on
an unknown dimension, or quoting anything but a user's own words, is rejected
there.  Any failure here proposes nothing, so the state stays as it was and the
Planner still runs.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from app.core.exceptions import PermanentModelError, RetryableModelError
from app.core.gateway.base import ModelGateway
from app.modules.conversations.state_update import Message
from app.modules.runtime.context.engine import build_context
from app.modules.runtime.context.policies.state_extract import STATE_EXTRACT
from app.modules.runtime.model_governance import (
    ModelBudgetExceeded,
    model_context_scope,
)
from app.modules.runtime.prompts import get_prompt_registry

# The messages shown before the current one.
RECENT_MESSAGES = 8
MAX_STATE_UPDATES = 8

# Why nothing was proposed.
OVER_BUDGET = "context_over_budget"
MODEL_ERROR = "model_error"
# The task's extraction allowance is spent (M7c); the answer path is not.
BUDGET_EXHAUSTED = "model_budget_exhausted"
INVALID_OUTPUT = "invalid_output"


@dataclass(frozen=True)
class Extraction:
    updates: list[dict] = field(default_factory=list)
    error: str | None = None


def _as_dict(message: Message) -> dict:
    return {"id": message.id, "role": message.role, "content": message.content or ""}


def render_prompt(payload: dict[str, Any]) -> str:
    """The user prompt, from what the policy let through."""
    messages = (payload.get("history") or {}).get("messages", [])

    def dumps(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False)

    return "\n".join(
        [
            f"<current_state>{dumps(payload['current_state'])}</current_state>",
            f"<messages>{dumps(messages)}</messages>",
            f"<current_message>{dumps(payload['current_message'])}</current_message>",
        ]
    )


def parse_output(raw: str) -> Extraction:
    """Keep the object items of ``state_update``; anything else proposes nothing."""
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return Extraction(error=INVALID_OUTPUT)
    if not isinstance(data, dict) or not isinstance(data.get("state_update"), list):
        return Extraction(error=INVALID_OUTPUT)
    items = [item for item in data["state_update"] if isinstance(item, dict)]
    return Extraction(items[:MAX_STATE_UPDATES])


def extract_state_update(
    gateway: ModelGateway,
    *,
    state: dict,
    history: Sequence[Message],
    current: Message,
) -> Extraction:
    """Proposals for ``current``; ``history`` is the messages before it."""
    system_prompt = get_prompt_registry().text("conversation.state_extract")
    build = build_context(
        STATE_EXTRACT,
        {
            "history": {"messages": [_as_dict(m) for m in history[-RECENT_MESSAGES:]]},
            "system": system_prompt,
            "current_state": state.get("constraints", {}),
            "current_message": {"id": current.id, "content": current.content or ""},
        },
    )
    if not build.fits:
        return Extraction(error=OVER_BUDGET)
    with model_context_scope(build.manifest):
        try:
            raw = gateway.chat(
                prompt=render_prompt(build.payload),
                system_prompt=system_prompt,
                json_mode=True,
            )
        except (RetryableModelError, PermanentModelError):
            return Extraction(error=MODEL_ERROR)
        except ModelBudgetExceeded:
            return Extraction(error=BUDGET_EXHAUSTED)
    return parse_output(raw)
