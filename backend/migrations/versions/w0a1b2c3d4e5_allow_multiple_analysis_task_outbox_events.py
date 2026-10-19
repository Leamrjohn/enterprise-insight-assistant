"""allow multiple analysis task outbox events

Revision ID: w0a1b2c3d4e5
Revises: v9a0b1c2d3e4
"""

from collections.abc import Sequence

from alembic import op

revision: str = "w0a1b2c3d4e5"
down_revision: str | Sequence[str] | None = "v9a0b1c2d3e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_analysis_task_outbox_events_task_id",
        "analysis_task_outbox_events",
        type_="unique",
    )
    op.create_index(
        "ix_analysis_task_outbox_events_task_id",
        "analysis_task_outbox_events",
        ["task_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_analysis_task_outbox_events_task_id",
        table_name="analysis_task_outbox_events",
    )
    op.create_unique_constraint(
        "uq_analysis_task_outbox_events_task_id",
        "analysis_task_outbox_events",
        ["task_id"],
    )
