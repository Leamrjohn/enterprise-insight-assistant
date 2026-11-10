"""Add analysis_tasks.config_snapshot and config_snapshot_hash (K4).

The business configuration (context, memory, rag, flags, tool domains) a task
was created with, and the sha256 of its canonical JSON.  Nullable, no backfill:
older tasks keep reading the current settings.

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d6e7f8a9b0c1"
down_revision = "c5d6e7f8a9b0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "analysis_tasks",
        sa.Column("config_snapshot", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "analysis_tasks",
        sa.Column("config_snapshot_hash", sa.String(64), nullable=True),
    )
    op.create_index(
        "ix_analysis_tasks_config_snapshot_hash",
        "analysis_tasks",
        ["config_snapshot_hash"],
    )


def downgrade() -> None:
    op.drop_index("ix_analysis_tasks_config_snapshot_hash", table_name="analysis_tasks")
    op.drop_column("analysis_tasks", "config_snapshot_hash")
    op.drop_column("analysis_tasks", "config_snapshot")
