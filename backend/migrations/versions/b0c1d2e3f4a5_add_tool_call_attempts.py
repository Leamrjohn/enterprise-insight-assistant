"""Add logical_call_id, attempt_no, error_class to tool_call_records (T4).

One row per actual execution; retries of one logical call share
logical_call_id.  New columns only: old rows keep NULL logical_call_id
(not backfilled) and attempt_no 1.

Revision ID: b0c1d2e3f4a5
Revises: a9b0c1d2e3f4
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b0c1d2e3f4a5"
down_revision = "a9b0c1d2e3f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tool_call_records",
        sa.Column("logical_call_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "tool_call_records",
        sa.Column("attempt_no", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "tool_call_records", sa.Column("error_class", sa.String(16), nullable=True)
    )
    op.create_index(
        "ix_tool_call_records_logical", "tool_call_records", ["logical_call_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_tool_call_records_logical", table_name="tool_call_records")
    op.drop_column("tool_call_records", "error_class")
    op.drop_column("tool_call_records", "attempt_no")
    op.drop_column("tool_call_records", "logical_call_id")
