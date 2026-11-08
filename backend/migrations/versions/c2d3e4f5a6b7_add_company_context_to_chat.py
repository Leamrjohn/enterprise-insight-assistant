"""add immutable company context fields to chat records

Revision ID: c2d3e4f5a6b7
Revises: b1a2c3d4e5f6
"""

from alembic import op
import sqlalchemy as sa

revision = "c2d3e4f5a6b7"
down_revision = "b1a2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("conversations", "documents", "analysis_tasks"):
        op.add_column(table, sa.Column("company_id", sa.Integer(), nullable=True))
        op.create_foreign_key(
            f"fk_{table}_company_id_companies",
            table,
            "companies",
            ["company_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.add_column(
        "conversations", sa.Column("data_source_id", sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        "fk_conversations_data_source_id_business_data_sources",
        "conversations",
        "business_data_sources",
        ["data_source_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "analysis_tasks", sa.Column("data_source_id", sa.Integer(), nullable=True)
    )
    op.add_column(
        "analysis_tasks", sa.Column("schema_snapshot_id", sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        "fk_analysis_tasks_data_source_id_business_data_sources",
        "analysis_tasks",
        "business_data_sources",
        ["data_source_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_analysis_tasks_schema_snapshot_id_schema_snapshots",
        "analysis_tasks",
        "schema_snapshots",
        ["schema_snapshot_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    raise NotImplementedError(
        "Downgrade is intentionally not supported for tenant-context migration"
    )
