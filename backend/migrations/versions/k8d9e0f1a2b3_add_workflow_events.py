"""add append-only workflow audit events

Revision ID: k8d9e0f1a2b3
Revises: j7c8d9e0f1a2
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "k8d9e0f1a2b3"
down_revision = "j7c8d9e0f1a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workflow_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("execution_attempt_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer()),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("node_name", sa.String(length=64)),
        sa.Column("tool_name", sa.String(length=64)),
        sa.Column("status", sa.String(length=32)),
        sa.Column("error_code", sa.String(length=128)),
        sa.Column(
            "details",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["task_id"], ["analysis_tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["execution_attempt_id"],
            ["task_execution_attempts.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "execution_attempt_id", "sequence", name="uq_workflow_event_sequence"
        ),
    )
    op.create_index("ix_workflow_events_task_id", "workflow_events", ["task_id"])
    op.create_index(
        "ix_workflow_events_execution_attempt_id",
        "workflow_events",
        ["execution_attempt_id"],
    )
    op.create_index("ix_workflow_events_company_id", "workflow_events", ["company_id"])
    op.create_index("ix_workflow_events_event_type", "workflow_events", ["event_type"])
    op.create_index("ix_workflow_events_created_at", "workflow_events", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_workflow_events_created_at", table_name="workflow_events")
    op.drop_index("ix_workflow_events_event_type", table_name="workflow_events")
    op.drop_index("ix_workflow_events_company_id", table_name="workflow_events")
    op.drop_index(
        "ix_workflow_events_execution_attempt_id", table_name="workflow_events"
    )
    op.drop_index("ix_workflow_events_task_id", table_name="workflow_events")
    op.drop_table("workflow_events")
