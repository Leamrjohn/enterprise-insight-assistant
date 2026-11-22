"""Add conversation_summaries (C9).

One row per conversation: the summary of the messages that left the context
window, written by code after a task is published.  Same shape and RLS as
conversation_states, but its own table so the two writers keep separate
optimistic locks.  New table only, no backfill: a conversation without a row
has the empty summary.

Revision ID: a9b0c1d2e3f4
Revises: f8a9b0c1d2e3
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a9b0c1d2e3f4"
down_revision = "f8a9b0c1d2e3"
branch_labels = None
depends_on = None

_SCOPE = "NULLIF(current_setting('app.company_id', true), '')::integer"


def upgrade() -> None:
    op.create_table(
        "conversation_summaries",
        sa.Column(
            "conversation_id",
            sa.Integer(),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("summary", postgresql.JSONB(), nullable=False),
        sa.Column(
            "last_task_id",
            sa.Integer(),
            sa.ForeignKey("analysis_tasks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("version >= 1", name="version_positive"),
    )
    op.execute("ALTER TABLE conversation_summaries ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE conversation_summaries FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY conversation_summaries_tenant_scope ON conversation_summaries
        USING (company_id = {_SCOPE})
        WITH CHECK (company_id = {_SCOPE})
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY conversation_summaries_tenant_scope ON conversation_summaries"
    )
    op.drop_table("conversation_summaries")
