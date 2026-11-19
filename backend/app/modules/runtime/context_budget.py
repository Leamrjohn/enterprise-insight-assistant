"""Decide what each model call may see, and shrink it when it gets close to full.

Every node lists the sections and fields it needs; anything else stays out.
Shrinking only ever uses code, so nothing is reworded: repeated data is capped,
and the result says what was left out.  A section with no compressor is a
constraint and is never touched, even if that leaves the call over budget.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.core.config.context import ContextConfig
from app.core.config.snapshot import runtime_settings
from app.modules.runtime.context.engine import (
    ContextPolicy,
    SectionRule,
    build_context,
    count_tokens,
)
from app.modules.runtime.context.manifest import ContextManifest

__all__ = ["ContextPolicy", "Section", "assemble", "count_tokens"]

logger = logging.getLogger(__name__)

# Defaults only; the running values come from CONTEXT_* settings (K1).
MAX_ROWS_WHEN_COMPRESSED: int = ContextConfig.model_fields[
    "context_max_rows_when_compressed"
].default

# The evidence review's name for a section rule, kept from before the engine.
Section = SectionRule


@dataclass
class ContextDecision:
    node: str
    tokens: int
    budget_tokens: int
    left_out: list[str] = field(default_factory=list)
    compressed: list[str] = field(default_factory=list)
    over_budget: bool = False
    manifest: ContextManifest | None = None


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
    """The payload a node may send, and a record of what was done to it.

    Still sends an over-budget payload, as before C4: the evidence review moves
    to require_fit in C5.
    """
    build = build_context(policy, sections)
    actions = {entry.name: entry.action for entry in build.manifest.sections}
    decision = ContextDecision(
        node=policy.node,
        tokens=build.tokens,
        budget_tokens=policy.budget_tokens,
        left_out=[name for name, action in actions.items() if action == "left_out"],
        compressed=[name for name, action in actions.items() if action == "compressed"],
        over_budget=not build.fits,
        manifest=build.manifest,
    )
    if decision.left_out or decision.compressed or decision.over_budget:
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
    return build.payload, decision


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
