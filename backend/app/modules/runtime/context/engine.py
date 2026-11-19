"""Build what one model call may see, and say plainly when it does not fit (C4).

Steps, always in this order (design 02_context_engine.md, 2.2):
1. keep only the sections the policy lists, and only their whitelisted fields;
2. shrink any section over its own cap with its own compressor;
3. near the budget, shrink sections in policy order until under the threshold;
4. still over: drop droppable sections in policy order until it fits;
5. still over: the verdict is the policy's on_over_budget, never "send anyway".

Only code shrinks anything, so nothing is reworded.  The same input always
gives the same result, which is what lets a checkpoint replay it.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from app.core.config.snapshot import runtime_settings
from app.core.tokenizer import count_tokens as count_text_tokens
from app.modules.runtime.context.manifest import (
    ContextManifest,
    SectionEntry,
    content_hash,
)

Verdict = Literal["fits", "reject", "clarify"]


@dataclass(frozen=True)
class SectionRule:
    # Only these keys of a dict section are kept; None keeps the whole value.
    fields: tuple[str, ...] | None = None
    compress: Callable[[Any], Any] | None = None
    # Over this many tokens the section is shrunk on its own, budget or not.
    max_tokens: int | None = None
    # May be left out whole when nothing else makes the call fit.
    droppable: bool = False
    # Missing from the input is a bug in the caller, not something to send.
    required: bool = False


@dataclass(frozen=True)
class ContextPolicy:
    node: str
    # "<node>/<n>": recorded with every call; raise n whenever the sections,
    # fields or budget change, so ledger rows can be compared per version.
    version: str
    budget_tokens: int
    # In the order to shrink and drop them: the first entry gives way first.
    sections: dict[str, SectionRule]
    # Kept free for the model's answer.
    output_reserve_tokens: int = 0
    on_over_budget: Literal["reject", "clarify"] = "reject"

    @property
    def available_tokens(self) -> int:
        return self.budget_tokens - self.output_reserve_tokens


@dataclass(frozen=True)
class ContextBuild:
    payload: dict[str, Any]
    tokens: int
    verdict: Verdict
    manifest: ContextManifest

    @property
    def fits(self) -> bool:
        return self.verdict == "fits"


class ContextBudgetExceeded(Exception):
    """Raised before any model budget is reserved, so nothing is charged."""

    def __init__(self, build: ContextBuild) -> None:
        super().__init__(
            f"{build.manifest.policy}: {build.tokens} tokens do not fit"
            f" {build.manifest.budget_tokens}"
        )
        self.build = build
        self.action = build.verdict


def count_tokens(value: Any) -> int:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return count_text_tokens(text)


def build_context(policy: ContextPolicy, sections: dict[str, Any]) -> ContextBuild:
    """The payload this policy allows, what was done to it, and whether it fits."""
    missing = [
        name
        for name, rule in policy.sections.items()
        if rule.required and name not in sections
    ]
    if missing:
        raise ValueError(f"{policy.version}: required sections missing: {missing}")

    # 1. Filter.
    payload: dict[str, Any] = {}
    filtered: list[str] = []
    for name, rule in policy.sections.items():
        if name not in sections:
            continue
        value = sections[name]
        if rule.fields is not None and isinstance(value, dict):
            value = {key: value[key] for key in rule.fields if key in value}
            if value != sections[name]:
                filtered.append(name)
        payload[name] = value

    # 2. Per-section caps.
    capped: list[str] = []
    for name, rule in policy.sections.items():
        if rule.max_tokens is None or rule.compress is None or name not in payload:
            continue
        if count_tokens(payload[name]) > rule.max_tokens:
            shrunk = rule.compress(payload[name])
            if shrunk != payload[name]:
                payload[name] = shrunk
                capped.append(name)

    # 3. Shrink near the budget.
    tokens = count_tokens(payload)
    compressed: list[str] = []
    threshold = policy.available_tokens * runtime_settings().context_compress_at
    for name, rule in policy.sections.items():
        if tokens < threshold:
            break
        if rule.compress is None or name not in payload or name in capped:
            continue
        shrunk = rule.compress(payload[name])
        if shrunk != payload[name]:
            payload[name] = shrunk
            compressed.append(name)
            tokens = count_tokens(payload)

    # 4. Drop what may go, 5. decide.
    dropped: list[str] = []
    for name, rule in policy.sections.items():
        if tokens <= policy.available_tokens:
            break
        if not rule.droppable or name not in payload:
            continue
        del payload[name]
        dropped.append(name)
        tokens = count_tokens(payload)

    verdict: Verdict = (
        "fits" if tokens <= policy.available_tokens else policy.on_over_budget
    )

    return ContextBuild(
        payload=payload,
        tokens=tokens,
        verdict=verdict,
        manifest=_manifest(
            policy,
            sections,
            payload,
            filtered=filtered,
            compressed=[*capped, *compressed],
            capped=capped,
            dropped=dropped,
            tokens=tokens,
            over_budget=verdict != "fits",
        ),
    )


def require_fit(build: ContextBuild) -> dict[str, Any]:
    """The payload to send, or ContextBudgetExceeded: never an over-budget call."""
    if not build.fits:
        raise ContextBudgetExceeded(build)
    return build.payload


def _manifest(
    policy: ContextPolicy,
    sections: dict[str, Any],
    payload: dict[str, Any],
    *,
    filtered: list[str],
    compressed: list[str],
    capped: list[str],
    dropped: list[str],
    tokens: int,
    over_budget: bool,
) -> ContextManifest:
    """Per section, in the order received: tokens given, tokens sent, and why."""
    entries: list[SectionEntry] = []
    for name, value in sections.items():
        if name not in payload:
            entries.append(
                SectionEntry(
                    name=name,
                    original_tokens=count_tokens(value),
                    final_tokens=0,
                    action="dropped" if name in dropped else "left_out",
                    reason="over_budget" if name in dropped else "not_in_policy",
                    content_hash=None,
                )
            )
            continue
        elif name in compressed:
            action = "compressed"
            reason = "section_cap" if name in capped else "near_budget"
        elif name in filtered:
            action = "filtered"
            reason = "field_whitelist"
        else:
            action = "kept"
            reason = None
        final_tokens = count_tokens(payload[name])
        digest = content_hash(payload[name])
        entries.append(
            SectionEntry(
                name=name,
                original_tokens=count_tokens(value),
                final_tokens=final_tokens,
                action=action,
                reason=reason,
                content_hash=digest,
            )
        )
    return ContextManifest(
        policy=policy.version,
        budget_tokens=policy.budget_tokens,
        estimated_tokens=tokens,
        over_budget=over_budget,
        sections=tuple(entries),
    )
