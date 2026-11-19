"""Decide what each model call may see, and shrink it when it gets close to full.

Every node lists the sections and fields it needs; anything else stays out.
Shrinking only ever uses code, so nothing is reworded: repeated data is capped,
and the result says what was left out.  A section with no compressor is a
constraint and is never touched, even if that leaves the call over budget.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.core.config.context import ContextConfig
from app.core.config.snapshot import runtime_settings
from app.core.tokenizer import count_tokens as count_text_tokens
from app.modules.runtime.context.manifest import (
    ContextManifest,
    SectionEntry,
    content_hash,
)

logger = logging.getLogger(__name__)

# Defaults only; the running values come from CONTEXT_* settings (K1).
MAX_ROWS_WHEN_COMPRESSED: int = ContextConfig.model_fields[
    "context_max_rows_when_compressed"
].default


@dataclass(frozen=True)
class Section:
    # Only these keys of a dict section are kept; None keeps the whole value.
    fields: tuple[str, ...] | None = None
    compress: Callable[[Any], Any] | None = None


@dataclass(frozen=True)
class ContextPolicy:
    node: str
    # "<node>/<n>": recorded with every call; raise n whenever the sections,
    # fields or budget change, so ledger rows can be compared per version.
    version: str
    budget_tokens: int
    # In the order to shrink them: the first entry gives way first.
    sections: dict[str, Section]


@dataclass
class ContextDecision:
    node: str
    tokens: int
    budget_tokens: int
    left_out: list[str] = field(default_factory=list)
    compressed: list[str] = field(default_factory=list)
    over_budget: bool = False
    manifest: ContextManifest | None = None


def count_tokens(value: Any) -> int:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return count_text_tokens(text)


def cap_data_rows(data_result: dict) -> dict:
    """Keep the first rows and say how many were dropped; the columns stay."""
    max_rows = runtime_settings().context_max_rows_when_compressed
    evidence = []
    for item in data_result.get("evidence") or []:
        rows = item.get("rows") if isinstance(item, dict) else None
        if isinstance(rows, list) and len(rows) > max_rows:
            item = {
                **item,
                "rows": rows[:max_rows],
                "rows_left_out": len(rows) - max_rows,
            }
        evidence.append(item)
    return {**data_result, "evidence": evidence}


def cap_chunk_text(knowledge_result: dict) -> dict:
    """Shorten long chunks and mark them, so a model can't read absence as fact."""
    max_chars = runtime_settings().context_max_chunk_chars_when_compressed
    evidences = []
    for item in knowledge_result.get("evidences") or []:
        content = item.get("content") if isinstance(item, dict) else None
        if isinstance(content, str) and len(content) > max_chars:
            item = {
                **item,
                "content": content[:max_chars],
                "content_truncated": True,
            }
        evidences.append(item)
    return {**knowledge_result, "evidences": evidences}


def assemble(
    policy: ContextPolicy, sections: dict[str, Any]
) -> tuple[dict[str, Any], ContextDecision]:
    """The payload a node may send, and a record of what was done to it."""
    payload: dict[str, Any] = {}
    left_out = [name for name in sections if name not in policy.sections]
    filtered = []
    for name, rule in policy.sections.items():
        if name not in sections:
            continue
        value = sections[name]
        if rule.fields is not None and isinstance(value, dict):
            value = {key: value[key] for key in rule.fields if key in value}
            if value != sections[name]:
                filtered.append(name)
        payload[name] = value

    tokens = count_tokens(payload)
    compressed = []
    threshold = policy.budget_tokens * runtime_settings().context_compress_at
    for name, rule in policy.sections.items():
        if tokens < threshold:
            break
        if rule.compress is None or name not in payload:
            continue
        shrunk = rule.compress(payload[name])
        if shrunk != payload[name]:
            payload[name] = shrunk
            compressed.append(name)
            tokens = count_tokens(payload)

    over_budget = tokens > policy.budget_tokens
    decision = ContextDecision(
        node=policy.node,
        tokens=tokens,
        budget_tokens=policy.budget_tokens,
        left_out=left_out,
        compressed=compressed,
        over_budget=over_budget,
        manifest=_manifest(
            policy, sections, payload, filtered, compressed, tokens, over_budget
        ),
    )
    if left_out or compressed or decision.over_budget:
        logger.info(
            "Model context adjusted",
            extra={
                "context_node": decision.node,
                "context_tokens": decision.tokens,
                "context_budget_tokens": decision.budget_tokens,
                "context_left_out": decision.left_out,
                "context_compressed": decision.compressed,
                "context_over_budget": decision.over_budget,
            },
        )
    return payload, decision


def _manifest(
    policy: ContextPolicy,
    sections: dict[str, Any],
    payload: dict[str, Any],
    filtered: list[str],
    compressed: list[str],
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
                    action="left_out",
                    reason="not_in_policy",
                    content_hash=None,
                )
            )
            continue
        elif name in compressed:
            action = "compressed"
            reason = "near_budget"
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


_PLAN_FIELDS = ("action", "route", "resolved_question", "intent", "evaluation_scope")
_REPORT_FIELDS = (
    "status",
    "executive_summary",
    "confirmed_facts",
    "hypotheses",
    "document_findings",
    "limitations",
)

# The report's data_evidence and document_citations repeat data_result and
# knowledge_result, which are in the same payload.
EVIDENCE_REVIEW = ContextPolicy(
    node="evidence_review",
    version="evidence_review/1",
    budget_tokens=4000,
    sections={
        "data_result": Section(
            fields=("status", "evidence", "error_code"), compress=cap_data_rows
        ),
        "knowledge_result": Section(
            fields=("status", "answer", "evidences", "error_code"),
            compress=cap_chunk_text,
        ),
        "deterministic_report": Section(fields=_REPORT_FIELDS),
        "memories_used": Section(),
        "plan": Section(fields=_PLAN_FIELDS),
        "question": Section(),
    },
)
