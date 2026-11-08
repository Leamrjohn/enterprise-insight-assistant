"""add frozen workflow release selection and retry rollback

Revision ID: s6d7e8f9a0b1
Revises: r5c6d7e8f9a0
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "s6d7e8f9a0b1"
down_revision = "r5c6d7e8f9a0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "analysis_tasks",
        sa.Column(
            "workflow_policy_snapshot",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text(
                "'{\"version\": \"v1\", \"rollback_version\": \"v1\"}'::jsonb"
            ),
        ),
    )
    op.add_column(
        "analysis_tasks", sa.Column("workflow_version_override", sa.String(64))
    )


def downgrade() -> None:
    op.drop_column("analysis_tasks", "workflow_version_override")
    op.drop_column("analysis_tasks", "workflow_policy_snapshot")
