"""add cancelled state to analysis task outbox

Revision ID: v9a0b1c2d3e4
Revises: u8f9a0b1c2d3
"""

from typing import Sequence, Union

from alembic import op


revision: str = "v9a0b1c2d3e4"
down_revision: Union[str, Sequence[str], None] = "u8f9a0b1c2d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "analysis_task_outbox_status_values",
        "analysis_task_outbox_events",
        type_="check",
    )
    op.create_check_constraint(
        "analysis_task_outbox_status_values",
        "analysis_task_outbox_events",
        "status IN ('pending', 'publishing', 'broker_accepted', 'worker_claimed', 'cancelled')",
    )


def downgrade() -> None:
    # The older schema has no terminal "cancelled before claim" representation.
    # Keep it non-republishable and preserve the reason in `last_error`.
    op.execute(
        """
        UPDATE analysis_task_outbox_events
        SET status = 'worker_claimed',
            last_error = 'cancelled before worker claim; downgraded from cancelled'
        WHERE status = 'cancelled'
        """
    )
    op.drop_constraint(
        "analysis_task_outbox_status_values",
        "analysis_task_outbox_events",
        type_="check",
    )
    op.create_check_constraint(
        "analysis_task_outbox_status_values",
        "analysis_task_outbox_events",
        "status IN ('pending', 'publishing', 'broker_accepted', 'worker_claimed')",
    )
