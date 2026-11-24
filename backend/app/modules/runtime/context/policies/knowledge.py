"""What the Knowledge answer may see (design 02_context_engine.md, 2.3).

knowledge_answer/1 only measured: build_prompt picked whole chunks by its
3000-character cap.  knowledge_answer/2 (C7): a chunk past the cap is cut to
the sentences about the question instead of being dropped (fit_evidences), so
a prompt can change; the engine still only measures.

Raise the version whenever a section, field or number here changes.
"""

from app.modules.runtime.context.engine import ContextPolicy, SectionRule

KNOWLEDGE_ANSWER = ContextPolicy(
    node="knowledge_answer",
    version="knowledge_answer/2",
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
