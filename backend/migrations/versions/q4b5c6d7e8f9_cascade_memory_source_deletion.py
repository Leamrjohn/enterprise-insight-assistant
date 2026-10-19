"""cascade memory deletion when its provenance source is deleted

Revision ID: q4b5c6d7e8f9
Revises: p3a4b5c6d7e8
"""

from alembic import op

revision = "q4b5c6d7e8f9"
down_revision = "p3a4b5c6d7e8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "analysis_memories_memory_source_id_fkey",
        "analysis_memories",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "analysis_memories_memory_source_id_fkey",
        "analysis_memories",
        "memory_sources",
        ["memory_source_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "analysis_memories_memory_source_id_fkey",
        "analysis_memories",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "analysis_memories_memory_source_id_fkey",
        "analysis_memories",
        "memory_sources",
        ["memory_source_id"],
        ["id"],
        ondelete="SET NULL",
    )
