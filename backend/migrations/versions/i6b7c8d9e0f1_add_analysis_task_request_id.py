"""persist HTTP request correlation on analysis tasks

Revision ID: i6b7c8d9e0f1
Revises: h5a6b7c8d9e0
"""

from alembic import op
import sqlalchemy as sa


revision = "i6b7c8d9e0f1"
down_revision = "h5a6b7c8d9e0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "analysis_tasks", sa.Column("request_id", sa.String(128), nullable=True)
    )
    op.create_index("ix_analysis_tasks_request_id", "analysis_tasks", ["request_id"])


def downgrade() -> None:
    op.drop_index("ix_analysis_tasks_request_id", table_name="analysis_tasks")
    op.drop_column("analysis_tasks", "request_id")
