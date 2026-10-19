"""add claimed delivery state to analysis task outbox

Revision ID: t7e8f9a0b1c2
Revises: s6d7e8f9a0b1
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "t7e8f9a0b1c2"
down_revision: Union[str, Sequence[str], None] = "s6d7e8f9a0b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "analysis_task_outbox_status_values",
        "analysis_task_outbox_events",
        type_="check",
    )
    op.add_column(
        "analysis_task_outbox_events",
        sa.Column("publish_generation", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("analysis_task_outbox_events", sa.Column("publish_execution_id", sa.String(36)))
    op.add_column("analysis_task_outbox_events", sa.Column("publish_lease_expires_at", sa.DateTime(timezone=True)))
    op.add_column("analysis_task_outbox_events", sa.Column("broker_message_id", sa.String(255)))
    op.add_column("analysis_task_outbox_events", sa.Column("broker_accepted_at", sa.DateTime(timezone=True)))
    op.add_column("analysis_task_outbox_events", sa.Column("worker_claimed_at", sa.DateTime(timezone=True)))
    op.add_column("analysis_task_outbox_events", sa.Column("worker_execution_id", sa.String(36)))
    # The old `published` state proved only that enqueue returned.  Preserve a
    # completed historical task as a legacy delivered record, but requeue a
    # still-queued/retrying task because no Worker claim was ever persisted.
    op.execute(
        """
        UPDATE analysis_task_outbox_events AS event
        SET status = CASE
                WHEN task.status IN ('queued', 'retrying') THEN 'pending'
                ELSE 'worker_claimed'
            END,
            worker_claimed_at = CASE
                WHEN task.status IN ('queued', 'retrying') THEN NULL
                ELSE event.published_at
            END
        FROM analysis_tasks AS task
        WHERE event.task_id = task.id AND event.status = 'published'
        """
    )
    op.create_check_constraint(
        "analysis_task_outbox_status_values",
        "analysis_task_outbox_events",
        "status IN ('pending', 'publishing', 'broker_accepted', 'worker_claimed')",
    )
    op.create_index(
        "ix_analysis_task_outbox_events_publish_lease_expires_at",
        "analysis_task_outbox_events",
        ["publish_lease_expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_analysis_task_outbox_events_publish_lease_expires_at", table_name="analysis_task_outbox_events")
    op.drop_constraint("analysis_task_outbox_status_values", "analysis_task_outbox_events", type_="check")
    op.create_check_constraint("analysis_task_outbox_status_values", "analysis_task_outbox_events", "status IN ('pending', 'published')")
    for name in ("worker_execution_id", "worker_claimed_at", "broker_accepted_at", "broker_message_id", "publish_lease_expires_at", "publish_execution_id", "publish_generation"):
        op.drop_column("analysis_task_outbox_events", name)
