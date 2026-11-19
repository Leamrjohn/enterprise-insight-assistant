"""The ledger record of how a model call's context was built (C3).

One entry per section: tokens before and after, what was done to it and why,
and a hash of what was sent.  Never the text itself, so the ledger can be
read without seeing company data.  Written to model_call_records by
reserve_model_call, in the same commit as the reservation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Literal

# kept: sent as given; filtered: only whitelisted fields sent;
# compressed: shortened by its compressor; left_out: not sent at all.
Action = Literal["kept", "filtered", "compressed", "left_out"]


def content_hash(value: Any) -> str:
    """Same value, same hash, whatever the key order."""
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SectionEntry:
    name: str
    original_tokens: int
    final_tokens: int
    action: Action
    reason: str | None = None
    # None when the section was left out: nothing was sent to hash.
    content_hash: str | None = None


@dataclass(frozen=True)
class ContextManifest:
    policy: str  # e.g. "evidence_review/1"
    budget_tokens: int
    estimated_tokens: int
    over_budget: bool
    sections: tuple[SectionEntry, ...]

    def to_record(self) -> dict[str, Any]:
        return {
            "policy": self.policy,
            "budget": self.budget_tokens,
            "estimated_tokens": self.estimated_tokens,
            "over_budget": self.over_budget,
            "sections": [
                {
                    "name": entry.name,
                    "original": entry.original_tokens,
                    "final": entry.final_tokens,
                    "action": entry.action,
                    "reason": entry.reason,
                    "hash": entry.content_hash,
                }
                for entry in self.sections
            ],
        }
