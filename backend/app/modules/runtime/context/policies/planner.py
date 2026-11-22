"""What the Planner may see (design 02_context_engine.md, 2.3).

Raise the version whenever a section, field or number here changes.
"""

from app.modules.runtime.context.compressors import compress_history
from app.modules.runtime.context.engine import ContextPolicy, SectionRule

PLANNER = ContextPolicy(
    node="planner",
    # 2: history is compressed by shortening assistant replies, not dropping turns.
    # 3: history may carry the conversation state and the question's message id.
    # 4: the state is read-only, so the question's message id is no longer sent.
    version="planner/4",
    budget_tokens=3000,
    output_reserve_tokens=512,
    sections={
        # First entries give way first.
        "attachments": SectionRule(droppable=True),
        "memory": SectionRule(droppable=True),
        # The conversation service's own selection record is not for the model.
        "history": SectionRule(
            fields=(
                "messages",
                "history_truncated",
                "standing_constraints",
                "conversation_state",
            ),
            compress=compress_history,
        ),
        "feedback": SectionRule(),
        "retry": SectionRule(),
        "system": SectionRule(required=True),
        "question": SectionRule(required=True),
    },
    on_over_budget="clarify",
)
