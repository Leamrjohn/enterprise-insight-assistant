"""Plan rules over QuestionFacts (B2d: shadow, recorded beside the Planner's plan).

A rule only suggests a decision; nothing here changes the plan. Each hit is compared
with the Planner's final decision, and the offline evaluation scores each rule against
the routing labels, so B2e can enable rules one at a time on evidence.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.modules.analysis.planner.facts import FACTS_VERSION, QuestionFacts

RULES_VERSION = "rules/2"


@dataclass(frozen=True)
class PlanRule:
    rule_id: str
    # "action/route", the same label the routing evaluation uses.
    suggests: str
    applies: Callable[[QuestionFacts], bool]


def _has_time(facts: QuestionFacts) -> bool:
    return bool(facts.periods) or facts.period_is_relative


# rules/1 split on asks_quantity and was wrong on tasks 861/863/864: a number can come
# from a document (计提比例, 周转天数), and "请给出…销售额" asks for data without 多少.
def _document_only(facts: QuestionFacts) -> bool:
    return facts.wants_document and not facts.asks_business_metric


def _document_and_metric(facts: QuestionFacts) -> bool:
    return facts.wants_document and facts.asks_business_metric


def _number_without_time(facts: QuestionFacts) -> bool:
    # A number from a document ("按什么比例计提") needs no time range.
    return facts.asks_quantity and not facts.wants_document and not _has_time(facts)


def _comparison_without_time(facts: QuestionFacts) -> bool:
    # Conservative: "华东和华北8月对比" compares regions, so one period is enough.
    return facts.is_comparison and not _has_time(facts)


PLAN_RULES: tuple[PlanRule, ...] = (
    PlanRule("R2", "analyze/knowledge_only", _document_only),
    PlanRule("R3", "analyze/hybrid", _document_and_metric),
    PlanRule("R4", "needs_clarification/None", _number_without_time),
    PlanRule("R5", "needs_clarification/None", _comparison_without_time),
)


def plan_label(plan: dict | None) -> str | None:
    if not plan or not plan.get("action"):
        return None
    return f"{plan['action']}/{plan.get('route')}"


def matching_rules(facts: QuestionFacts) -> list[PlanRule]:
    return [rule for rule in PLAN_RULES if rule.applies(facts)]


# B2j arbitration table (decided by the user, 2026-11-07):
# 1. Hits that agree decide together. A routing rule (R2/R3) beats a clarification
#    rule (R5): a document question needs no period. Any other disagreement abstains
#    and leaves the decision to the Planner.
# 2. Rules read the Planner's resolved question when there is one, else the original,
#    so they see the same question as the Data and Knowledge nodes.
ROUTING_RULES = frozenset({"R2", "R3"})


def arbitrate(hits: list[PlanRule]) -> str | None:
    """The decision the hits make together, or None to leave it to the Planner."""
    if not hits:
        return None
    suggests = {rule.suggests for rule in hits}
    if len(suggests) == 1:
        return hits[0].suggests
    routing = [rule for rule in hits if rule.rule_id in ROUTING_RULES]
    routing_suggests = {rule.suggests for rule in routing}
    if len(routing_suggests) == 1:
        return routing[0].suggests
    return None


def rule_question(original: str, plan: dict | None) -> tuple[str, str]:
    """The question the rules read, and "resolved" or "original" for the record."""
    resolved = (plan or {}).get("resolved_question")
    if resolved:
        return (resolved, "resolved")
    return (original, "original")


def shadow_details(facts: QuestionFacts, plan: dict | None) -> dict:
    """Rule ids and labels only; like the facts event, no question text."""
    planner = plan_label(plan)
    hits = matching_rules(facts)
    return {
        "version": RULES_VERSION,
        "facts_version": FACTS_VERSION,
        "planner": planner,
        "hits": [
            {
                "rule": rule.rule_id,
                "suggests": rule.suggests,
                "agrees": rule.suggests == planner,
            }
            for rule in hits
        ],
        # What the rules would decide if enabled (B2e); None leaves it to the Planner.
        "decided": arbitrate(hits),
    }
