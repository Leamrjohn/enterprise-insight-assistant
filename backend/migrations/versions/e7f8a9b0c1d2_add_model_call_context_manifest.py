"""Add model_call_records.context_policy and context_manifest (C3).

Which context policy built a model call, and what it did to each section
(tokens before and after, kept / filtered / compressed / left out, content
hash).  Nullable, no backfill: calls that no policy built keep only the C2
counts in resource_usage.

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "e7f8a9b0c1d2"
down_revision = "d6e7f8a9b0c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "model_call_records",
        sa.Column("context_policy", sa.String(64), nullable=True),
    )
    op.add_column(
        "model_call_records",
        sa.Column("context_manifest", postgresql.JSONB(), nullable=True),
    )
    op.create_index(
        "ix_model_call_records_context_policy",
        "model_call_records",
        ["context_policy"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_model_call_records_context_policy", table_name="model_call_records"
    )
    op.drop_column("model_call_records", "context_manifest")
    op.drop_column("model_call_records", "context_policy")
