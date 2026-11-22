"""Ask the model to merge messages that left the window into the summary (C9).

The summarizer only proposes.  apply_summary keeps the last word: an item
citing a message that does not exist, or one still in the window, is rejected
there.  Any failure here proposes nothing, so the summary stays as it was.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from app.core.exceptions import PermanentModelError, RetryableModelError
from app.core.gateway.base import ModelGateway
from app.modules.conversations.state_update import Message
from app.modules.conversations.summary import MAX_SUMMARY_ITEMS
from app.modules.runtime.context.engine import build_context
from app.modules.runtime.context.policies.summary import SUMMARY
from app.modules.runtime.model_governance import (
    ModelBudgetExceeded,
    model_context_scope,
)
from app.modules.runtime.prompts import get_prompt_registry

# Why nothing was proposed; the same codes as the state extractor.
OVER_BUDGET = "context_over_budget"
MODEL_ERROR = "model_error"
BUDGET_EXHAUSTED = "model_budget_exhausted"
INVALID_OUTPUT = "invalid_output"


@dataclass(frozen=True)
class Summarization:
    items: list[dict] = field(default_factory=list)
    error: str | None = None


def _as_dict(message: Message) -> dict:
    return {"id": message.id, "role": message.role, "content": message.content or ""}


def render_prompt(payload: dict[str, Any]) -> str:
    """The user prompt, from what the policy let through."""
    messages = payload["history"]["messages"]

    def dumps(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False)

    return "\n".join(
        [
            f"<current_summary>{dumps(payload['current_summary'])}</current_summary>",
            f"<messages>{dumps(messages)}</messages>",
        ]
    )


def parse_output(raw: str) -> Summarization:
    """Keep the object items of ``summary_items``; anything else proposes nothing.

    Twice the cap is let through so apply_summary can report the overflow.
    """
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return Summarization(error=INVALID_OUTPUT)
    if not isinstance(data, dict) or not isinstance(data.get("summary_items"), list):
        return Summarization(error=INVALID_OUTPUT)
    items = [item for item in data["summary_items"] if isinstance(item, dict)]
    return Summarization(items[: 2 * MAX_SUMMARY_ITEMS])


def summarize(
    gateway: ModelGateway, *, summary: dict, messages: Sequence[Message]
) -> Summarization:
    """The new item list for ``summary`` after ``messages`` left the window."""
    system_prompt = get_prompt_registry().text("conversation.summary")
    build = build_context(
        SUMMARY,
        {
            "history": {"messages": [_as_dict(m) for m in messages]},
            "system": system_prompt,
            "current_summary": summary.get("items", []),
        },
    )
    if not build.fits:
        return Summarization(error=OVER_BUDGET)
    with model_context_scope(build.manifest):
        try:
            raw = gateway.chat(
                prompt=render_prompt(build.payload),
                system_prompt=system_prompt,
                json_mode=True,
            )
        except (RetryableModelError, PermanentModelError):
            return Summarization(error=MODEL_ERROR)
        except ModelBudgetExceeded:
            return Summarization(error=BUDGET_EXHAUSTED)
    return parse_output(raw)
