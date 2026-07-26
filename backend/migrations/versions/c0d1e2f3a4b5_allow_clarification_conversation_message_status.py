"""Allow clarification requests to be shown as assistant messages.

Revision ID: c0d1e2f3a4b5
Revises: b9c0d1e2f3a4
Create Date: 2026-07-26
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "c0d1e2f3a4b5"
down_revision = "b9c0d1e2f3a4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "status_values",
        "conversation_messages",
        type_="check",
    )
    op.create_check_constraint(
        "status_values",
        "conversation_messages",
        "status IN ('queued', 'running', 'completed', 'partial', 'failed', "
        "'cancelled', 'needs_clarification')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "status_values",
        "conversation_messages",
        type_="check",
    )
    op.create_check_constraint(
        "status_values",
        "conversation_messages",
        "status IN ('queued', 'running', 'completed', 'partial', 'failed', 'cancelled')",
    )
