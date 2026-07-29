"""add execution heartbeat, checkpoint pointer and workflow version

Revision ID: l9e0f1a2b3c4
Revises: k8d9e0f1a2b3
"""

from alembic import op
import sqlalchemy as sa


revision = "l9e0f1a2b3c4"
down_revision = "k8d9e0f1a2b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "task_execution_attempts",
        sa.Column(
            "heartbeat_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.add_column(
        "task_execution_attempts",
        sa.Column("latest_checkpoint_id", sa.Integer()),
    )
    op.add_column(
        "task_execution_attempts",
        sa.Column(
            "workflow_version",
            sa.String(length=64),
            nullable=False,
            server_default="v1",
        ),
    )
    op.create_index(
        "ix_task_execution_attempts_heartbeat_at",
        "task_execution_attempts",
        ["heartbeat_at"],
    )
    op.create_index(
        "ix_task_execution_attempts_latest_checkpoint_id",
        "task_execution_attempts",
        ["latest_checkpoint_id"],
    )
    op.create_foreign_key(
        "task_execution_attempts_latest_checkpoint_id_fkey",
        "task_execution_attempts",
        "workflow_checkpoints",
        ["latest_checkpoint_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "task_execution_attempts_latest_checkpoint_id_fkey",
        "task_execution_attempts",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_task_execution_attempts_latest_checkpoint_id",
        table_name="task_execution_attempts",
    )
    op.drop_index(
        "ix_task_execution_attempts_heartbeat_at",
        table_name="task_execution_attempts",
    )
    op.drop_column("task_execution_attempts", "workflow_version")
    op.drop_column("task_execution_attempts", "latest_checkpoint_id")
    op.drop_column("task_execution_attempts", "heartbeat_at")
