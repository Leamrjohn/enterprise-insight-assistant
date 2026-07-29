"""add planner-only validated analysis memories

Revision ID: h5a6b7c8d9e0
Revises: g4a5b6c7d8e9
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "h5a6b7c8d9e0"
down_revision = "g4a5b6c7d8e9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analysis_memories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("source_task_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("memory_type", sa.String(32), nullable=False),
        sa.Column("content", postgresql.JSONB(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column(
            "revoked", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_task_id"], ["analysis_tasks.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_analysis_memories_company_id", "analysis_memories", ["company_id"]
    )
    op.create_index("ix_analysis_memories_user_id", "analysis_memories", ["user_id"])
    op.create_index(
        "ix_analysis_memories_source_task_id", "analysis_memories", ["source_task_id"]
    )
    op.create_index(
        "ix_analysis_memories_expires_at", "analysis_memories", ["expires_at"]
    )
    op.create_index("ix_analysis_memories_revoked", "analysis_memories", ["revoked"])


def downgrade() -> None:
    op.drop_index("ix_analysis_memories_revoked", table_name="analysis_memories")
    op.drop_index("ix_analysis_memories_expires_at", table_name="analysis_memories")
    op.drop_index("ix_analysis_memories_source_task_id", table_name="analysis_memories")
    op.drop_index("ix_analysis_memories_user_id", table_name="analysis_memories")
    op.drop_index("ix_analysis_memories_company_id", table_name="analysis_memories")
    op.drop_table("analysis_memories")
