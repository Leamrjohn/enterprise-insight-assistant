"""Add layers, metadata, lifecycle status and an audit trail to memories.

Revision ID: a3b4c5d6e7f8
Revises: z2a3b4c5d6e7
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "a3b4c5d6e7f8"
down_revision = "z2a3b4c5d6e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "analysis_memories",
        sa.Column("layer", sa.String(16), nullable=False, server_default="fact"),
    )
    op.add_column(
        "analysis_memories",
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
    )
    op.add_column(
        "analysis_memories",
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
    )
    op.add_column(
        "analysis_memories",
        sa.Column("importance", sa.Float(), nullable=False, server_default="0.5"),
    )
    op.add_column("analysis_memories", sa.Column("subject_key", sa.String(64)))
    op.add_column("analysis_memories", sa.Column("business_valid_until", sa.Date()))
    op.add_column(
        "analysis_memories", sa.Column("last_used_at", sa.DateTime(timezone=True))
    )
    op.add_column(
        "analysis_memories",
        sa.Column("use_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("analysis_memories", sa.Column("superseded_by_id", sa.Integer()))
    op.add_column(
        "analysis_memories", sa.Column("deleted_at", sa.DateTime(timezone=True))
    )
    op.create_foreign_key(
        "fk_analysis_memories_superseded_by",
        "analysis_memories",
        "analysis_memories",
        ["superseded_by_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "analysis_memories_layer",
        "analysis_memories",
        "layer IN ('session', 'fact', 'preference', 'experience')",
    )
    op.create_check_constraint(
        "analysis_memories_status",
        "analysis_memories",
        "status IN ('active', 'flagged', 'superseded', 'revoked', 'deleted')",
    )
    op.create_index(
        "ix_analysis_memories_selection",
        "analysis_memories",
        ["company_id", "user_id", "status"],
    )
    op.create_index(
        "ix_analysis_memories_subject",
        "analysis_memories",
        ["company_id", "user_id", "subject_key"],
    )
    op.execute("UPDATE analysis_memories SET status = 'revoked' WHERE revoked")

    op.create_table(
        "memory_audit_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        # Survives physical deletion, which is what makes deletion auditable.
        sa.Column(
            "memory_id",
            sa.Integer(),
            sa.ForeignKey("analysis_memories.id", ondelete="SET NULL"),
            index=True,
        ),
        sa.Column("original_memory_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("actor_kind", sa.String(16), nullable=False),
        sa.Column(
            "actor_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column("reason", sa.Text()),
        sa.Column("details", JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "actor_kind IN ('system', 'model', 'user')",
            name="memory_audit_events_actor_kind",
        ),
    )


def downgrade() -> None:
    op.drop_table("memory_audit_events")
    op.drop_index("ix_analysis_memories_subject", table_name="analysis_memories")
    op.drop_index("ix_analysis_memories_selection", table_name="analysis_memories")
    op.drop_constraint("analysis_memories_status", "analysis_memories", type_="check")
    op.drop_constraint("analysis_memories_layer", "analysis_memories", type_="check")
    op.drop_constraint(
        "fk_analysis_memories_superseded_by", "analysis_memories", type_="foreignkey"
    )
    for column in (
        "deleted_at",
        "superseded_by_id",
        "use_count",
        "last_used_at",
        "business_valid_until",
        "subject_key",
        "importance",
        "confidence",
        "status",
        "layer",
    ):
        op.drop_column("analysis_memories", column)
