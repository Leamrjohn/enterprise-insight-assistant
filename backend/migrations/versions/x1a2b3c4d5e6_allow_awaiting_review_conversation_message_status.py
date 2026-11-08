"""Allow awaiting-review assistant messages.

Revision ID: x1a2b3c4d5e6
Revises: w0a1b2c3d4e5
"""

from alembic import op


revision = "x1a2b3c4d5e6"
down_revision = "w0a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("status_values", "conversation_messages", type_="check")
    op.create_check_constraint(
        "status_values",
        "conversation_messages",
        "status IN ('queued', 'running', 'awaiting_review', 'completed', "
        "'partial', 'failed', 'cancelled', 'needs_clarification')",
    )


def downgrade() -> None:
    op.drop_constraint("status_values", "conversation_messages", type_="check")
    op.create_check_constraint(
        "status_values",
        "conversation_messages",
        "status IN ('queued', 'running', 'completed', 'partial', 'failed', "
        "'cancelled', 'needs_clarification')",
    )
