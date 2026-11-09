"""Add analysis_tasks.trace_context for distributed tracing (O1).

The W3C traceparent of the request that created the task; the worker continues
that trace.  Nullable, no default: older tasks simply start a new trace.

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
"""

import sqlalchemy as sa
from alembic import op

revision = "c5d6e7f8a9b0"
down_revision = "b4c5d6e7f8a9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "analysis_tasks",
        sa.Column("trace_context", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("analysis_tasks", "trace_context")
