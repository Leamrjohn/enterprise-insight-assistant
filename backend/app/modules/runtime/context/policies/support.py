"""What the support check may see (design 02_context_engine.md, 2.3).

support/1 shrinks nothing: the check judges each sentence against the chunks'
own words, so a shortened chunk could hide the very passage that supports a
sentence and get it removed.  A check that cannot fit is refused instead.

Raise the version whenever a section, field or number here changes.
"""

from app.modules.runtime.context.engine import ContextPolicy, SectionRule

SUPPORT = ContextPolicy(
    node="support_check",
    version="support/1",
    budget_tokens=3000,
    output_reserve_tokens=512,
    sections={
        "confirmed_facts": SectionRule(),
        "evidences": SectionRule(),
        "system": SectionRule(required=True),
        "question": SectionRule(required=True),
        "sentences": SectionRule(required=True),
    },
    on_over_budget="reject",
)
