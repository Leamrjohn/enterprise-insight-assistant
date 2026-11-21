"""Add conversation_states (C6).

One row per conversation: the standing constraints and the current subject,
written by code after a task is published.  ``version`` is the optimistic lock;
RLS keeps a company to its own rows.  New table only, no backfill: a
conversation without a row has the empty state.

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f8a9b0c1d2e3"
down_revision = "e7f8a9b0c1d2"
branch_labels = None
depends_on = None

_SCOPE = "NULLIF(current_setting('app.company_id', true), '')::integer"


def upgrade() -> None:
    op.create_table(
        "conversation_states",
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
        sa.Column("state", postgresql.JSONB(), nullable=False),
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
    op.execute("ALTER TABLE conversation_states ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE conversation_states FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY conversation_states_tenant_scope ON conversation_states
        USING (company_id = {_SCOPE})
        WITH CHECK (company_id = {_SCOPE})
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY conversation_states_tenant_scope ON conversation_states")
    op.drop_table("conversation_states")
