"""What SQL generation may see (design 02_context_engine.md, 2.3).

sql/1 shrinks nothing: the schema sits inside the system prompt, so the
engine only measures the call and refuses it when it cannot fit.  Moving the
tables into a section of their own changes the prompt and needs the SQL eval.

Raise the version whenever a section, field or number here changes.
"""

from app.modules.runtime.context.engine import ContextPolicy, SectionRule

SQL = ContextPolicy(
    node="sql_generation",
    version="sql/1",
    budget_tokens=4000,
    output_reserve_tokens=512,
    sections={
        "previous_sql": SectionRule(),
        "instructions": SectionRule(),
        "system": SectionRule(required=True),
        "question": SectionRule(required=True),
    },
    on_over_budget="reject",
)
