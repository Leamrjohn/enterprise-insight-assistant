"""add task execution attempts and workflow checkpoints

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "e2f3a4b5c6d7"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("analysis_tasks", sa.Column("active_execution_id", sa.String(36)))
    op.create_index(
        "ix_analysis_tasks_active_execution_id",
        "analysis_tasks",
        ["active_execution_id"],
    )
    op.create_table(
        "task_execution_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("execution_id", sa.String(36), nullable=False, unique=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("worker_id", sa.String(128)),
        sa.Column("celery_task_id", sa.String(64)),
        sa.Column("retry_number", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('running','retrying','completed','partial','failed','cancelled','expired','superseded')",
            name="task_execution_attempt_status_values",
        ),
        sa.ForeignKeyConstraint(["task_id"], ["analysis_tasks.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_task_execution_attempts_task_id", "task_execution_attempts", ["task_id"]
    )
    op.create_index(
        "ix_task_execution_attempts_status", "task_execution_attempts", ["status"]
    )
    op.create_index(
        "ix_task_execution_attempts_lease_expires_at",
        "task_execution_attempts",
        ["lease_expires_at"],
    )
    op.create_table(
        "workflow_checkpoints",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("execution_attempt_id", sa.Integer(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("completed_node", sa.String(64)),
        sa.Column("next_node", sa.String(64)),
        sa.Column(
            "state_patch",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("error_code", sa.String(128)),
        sa.Column("recovery_instruction", sa.String(128)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["execution_attempt_id"], ["task_execution_attempts.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "execution_attempt_id", "sequence", name="uq_workflow_checkpoint_sequence"
        ),
    )
    op.create_index(
        "ix_workflow_checkpoints_execution_attempt_id",
        "workflow_checkpoints",
        ["execution_attempt_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_workflow_checkpoints_execution_attempt_id",
        table_name="workflow_checkpoints",
    )
    op.drop_table("workflow_checkpoints")
    op.drop_index(
        "ix_task_execution_attempts_lease_expires_at",
        table_name="task_execution_attempts",
    )
    op.drop_index(
        "ix_task_execution_attempts_status", table_name="task_execution_attempts"
    )
    op.drop_index(
        "ix_task_execution_attempts_task_id", table_name="task_execution_attempts"
    )
    op.drop_table("task_execution_attempts")
    op.drop_index("ix_analysis_tasks_active_execution_id", table_name="analysis_tasks")
    op.drop_column("analysis_tasks", "active_execution_id")
