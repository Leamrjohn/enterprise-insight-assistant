"""add analysis outbox, task observability, and frontend stages

Revision ID: f6a7b8c9d0e1
Revises: c8d9e0f1a2b3
Create Date: 2026-07-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, Sequence[str], None] = "c8d9e0f1a2b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("analysis_tasks", sa.Column("celery_task_id", sa.String(length=64)))
    op.add_column("analysis_tasks", sa.Column("error_type", sa.String(length=128)))
    op.add_column("analysis_tasks", sa.Column("duration_ms", sa.Integer()))
    op.drop_constraint(
        "analysistask_task_stage_values", "analysis_tasks", type_="check"
    )
    # Historical RAG stages are retained as task history but normalized to the
    # closest frontend-visible workflow stage before the stricter constraint.
    op.execute(
        """
        UPDATE analysis_tasks
        SET stage = CASE stage
            WHEN 'search_evidence' THEN 'retrieving_knowledge'
            WHEN 'check_sufficiency' THEN 'retrieving_knowledge'
            WHEN 'build_prompt' THEN 'composing_report'
            WHEN 'call_model' THEN 'composing_report'
            WHEN 'save_result' THEN 'saving_result'
            ELSE stage
        END
        """
    )
    op.create_check_constraint(
        "analysistask_task_stage_values",
        "analysis_tasks",
        "stage IN ('queued','planning','querying_data','retrieving_knowledge','composing_report','saving_result','retrying','completed')",
    )
    op.create_table(
        "analysis_task_outbox_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="pending"
        ),
        sa.Column(
            "publish_attempt_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("last_error", sa.Text()),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'published')",
            name="analysis_task_outbox_status_values",
        ),
        sa.ForeignKeyConstraint(["task_id"], ["analysis_tasks.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("task_id", name="uq_analysis_task_outbox_events_task_id"),
    )
    op.create_index(
        "ix_analysis_task_outbox_events_status",
        "analysis_task_outbox_events",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_analysis_task_outbox_events_status",
        table_name="analysis_task_outbox_events",
    )
    op.drop_table("analysis_task_outbox_events")
    op.drop_constraint(
        "analysistask_task_stage_values", "analysis_tasks", type_="check"
    )
    op.create_check_constraint(
        "analysistask_task_stage_values",
        "analysis_tasks",
        "stage IN ('queued','search_evidence','check_sufficiency','build_prompt','call_model','save_result','completed')",
    )
    op.drop_column("analysis_tasks", "duration_ms")
    op.drop_column("analysis_tasks", "error_type")
    op.drop_column("analysis_tasks", "celery_task_id")
