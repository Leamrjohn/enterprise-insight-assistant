"""What plan review and SQL review may see (design 02_context_engine.md, 2.3).

Both shrink nothing yet: the engine measures each call and refuses one that
cannot fit.  Every payload key is a section, so none is left out.

Raise the version whenever a section, field or number here changes.
"""

from app.modules.runtime.context.engine import ContextPolicy, SectionRule

REVIEW_PLAN = ContextPolicy(
    node="review_plan",
    version="review_plan/1",
    budget_tokens=3000,
    output_reserve_tokens=256,
    sections={
        "schema_snapshot": SectionRule(),
        "filter_value_definitions": SectionRule(),
        "registered_metrics": SectionRule(),
        "current_scope": SectionRule(),
        "proposed_plan": SectionRule(required=True),
        "system": SectionRule(required=True),
        "question": SectionRule(required=True),
    },
    on_over_budget="reject",
)

REVIEW_SQL = ContextPolicy(
    node="review_sql",
    version="review_sql/1",
    budget_tokens=3000,
    output_reserve_tokens=256,
    sections={
        "schema_snapshot": SectionRule(),
        "filter_value_definitions": SectionRule(),
        "registered_metrics": SectionRule(),
        "plan": SectionRule(),
        "candidate": SectionRule(required=True),
        "system": SectionRule(required=True),
        "question": SectionRule(required=True),
    },
    on_over_budget="reject",
)
