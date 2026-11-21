"""What the Knowledge answer may see (design 02_context_engine.md, 2.3).

knowledge_answer/1 only measures: build_prompt still picks the chunks by its
3000-character cap, so the prompt is unchanged and needs no eval.  Dropping
low-ranked chunks by tokens instead changes the prompt: that is a /2 with the
Knowledge eval.

Raise the version whenever a section, field or number here changes.
"""

from app.modules.runtime.context.engine import ContextPolicy, SectionRule

KNOWLEDGE_ANSWER = ContextPolicy(
    node="knowledge_answer",
    version="knowledge_answer/1",
    budget_tokens=4000,
    output_reserve_tokens=1024,
    sections={
        "confirmed_facts": SectionRule(),
        "evidences": SectionRule(),
        "system": SectionRule(required=True),
        "question": SectionRule(required=True),
    },
    on_over_budget="reject",
)
