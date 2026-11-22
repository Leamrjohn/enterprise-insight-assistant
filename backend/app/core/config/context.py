"""How much conversation history and evidence a model prompt may carry."""

from __future__ import annotations

from typing import Literal

from pydantic import field_validator

from app.core.config.base import ConfigDomain, require_positive


class ContextConfig(ConfigDomain):
    # conversations/service.py: tokens of earlier turns passed to the Planner.
    context_history_max_tokens: int = 2048
    # runtime/context_budget.py: compress once a prompt reaches this share of
    # its budget, keeping at most these rows and characters per item.
    context_compress_at: float = 0.8
    context_max_rows_when_compressed: int = 20
    context_max_chunk_chars_when_compressed: int = 800
    # analysis/planner/planning.py (C4): off runs no engine; shadow still sends
    # the old prompt and records the engine's manifest as "<policy>:shadow";
    # enforce sends what the engine kept and asks back when it cannot fit.
    context_planner_mode: Literal["off", "shadow", "enforce"] = "shadow"
    # analysis/data/sql_generation.py (C4): the same three modes; enforce
    # refuses an SQL call that cannot fit instead of sending it.
    context_sql_mode: Literal["off", "shadow", "enforce"] = "shadow"
    # reporting/semantic_review_service.py (C5): plan, SQL and evidence review.
    # enforce refuses a review that cannot fit instead of sending it.
    context_review_mode: Literal["off", "shadow", "enforce"] = "shadow"
    # knowledge/rag/support.py and knowledge/agent.py (C5): the support check
    # and the Knowledge answer; enforce refuses a call that cannot fit.
    context_knowledge_mode: Literal["off", "shadow", "enforce"] = "shadow"
    # conversations/state.py (M7): off freezes no state; shadow extracts and
    # saves the state but the Planner still sees the regex constraints;
    # enforce gives the Planner the state instead of them.
    conversation_state_mode: Literal["off", "shadow", "enforce"] = "off"
    # conversations/summarizer.py (C9): off summarizes nothing; shadow
    # summarizes after each publish but the Planner does not see it; enforce
    # gives the Planner the summary as an untrusted section.
    conversation_summary_mode: Literal["off", "shadow", "enforce"] = "off"

    @field_validator(
        "context_history_max_tokens",
        "context_max_rows_when_compressed",
        "context_max_chunk_chars_when_compressed",
    )
    @classmethod
    def context_validate_positive_int(cls, value: int) -> int:
        return require_positive(value)

    @field_validator("context_compress_at")
    @classmethod
    def context_validate_share(cls, value: float) -> float:
        if not 0 < value <= 1:
            raise ValueError("Compression threshold must be in (0, 1]")
        return value
