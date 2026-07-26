"""enforce single-company membership and current snapshot metadata

Revision ID: a6b7c8d9e0f1
Revises: f5a6b7c8d9e0
"""

from alembic import op
import sqlalchemy as sa

revision = "a6b7c8d9e0f1"
down_revision = "f5a6b7c8d9e0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "company_members",
        sa.Column("status", sa.String(length=20), nullable=False, server_default="approved"),
    )
    op.add_column(
        "company_members",
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.add_column(
        "company_members",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.drop_constraint("uq_company_members_company_user", "company_members", type_="unique")
    op.create_unique_constraint("uq_company_members_user", "company_members", ["user_id"])
    op.add_column(
        "business_data_sources",
        sa.Column("active_schema_snapshot_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "schema_snapshots",
        sa.Column("discovered_by_user_id", sa.Integer(), nullable=True),
    )
    op.execute(
        "UPDATE schema_snapshots SET discovered_by_user_id = "
        "(SELECT company_members.user_id FROM company_members "
        "JOIN business_data_sources ON business_data_sources.company_id = company_members.company_id "
        "WHERE business_data_sources.id = schema_snapshots.data_source_id "
        "ORDER BY company_members.id LIMIT 1)"
    )
    op.alter_column("schema_snapshots", "discovered_by_user_id", nullable=False)
    op.create_foreign_key(
        "fk_data_sources_active_snapshot",
        "business_data_sources",
        "schema_snapshots",
        ["active_schema_snapshot_id"], ["id"], ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_schema_snapshots_discovered_by_user_id_users",
        "schema_snapshots",
        "users",
        ["discovered_by_user_id"], ["id"], ondelete="RESTRICT",
    )


def downgrade() -> None:
    raise NotImplementedError("single-company membership migration is irreversible")
