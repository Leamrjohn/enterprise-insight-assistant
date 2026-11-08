"""Add company-bound platform data connections and link business data sources (A11b).

Each existing source with a complete connection_config gets a connection of its own
company; an incomplete one stays unlinked, so it is refused before any connection.
Both old columns stay for one release.

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
"""

import sqlalchemy as sa
from alembic import op

revision = "b4c5d6e7f8a9"
down_revision = "a3b4c5d6e7f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_data_connections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("host", sa.String(255), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("database", sa.String(63), nullable=False),
        sa.Column("username", sa.String(63), nullable=False),
        sa.Column("schema_name", sa.String(63), nullable=False),
        sa.Column("credential_ref", sa.String(130), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_by_operator", sa.String(120), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("company_id", "name"),
    )
    op.create_index(
        "ix_platform_data_connections_company_id",
        "platform_data_connections",
        ["company_id"],
    )
    op.add_column(
        "business_data_sources",
        sa.Column(
            "connection_id",
            sa.Integer(),
            # NO ACTION: checked at statement end, so deleting a company that
            # cascades to both tables works; deleting a connection in use does not.
            sa.ForeignKey("platform_data_connections.id"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_business_data_sources_connection_id",
        "business_data_sources",
        ["connection_id"],
    )
    op.execute(
        """
        INSERT INTO platform_data_connections (
            company_id, name, host, port, database, username, schema_name,
            credential_ref, status, created_by_operator
        )
        SELECT
            company_id,
            'backfill:source-' || id,
            connection_config->>'host',
            (connection_config->>'port')::integer,
            connection_config->>'database',
            connection_config->>'user',
            COALESCE(connection_config->>'schema', 'public'),
            'env:' || credential_env_var,
            'active',
            'migration-a11b'
        FROM business_data_sources
        WHERE connection_config ?& array['host', 'port', 'database', 'user']
        """
    )
    op.execute(
        """
        UPDATE business_data_sources AS source
        SET connection_id = connection.id
        FROM platform_data_connections AS connection
        WHERE connection.company_id = source.company_id
          AND connection.name = 'backfill:source-' || source.id
        """
    )


def downgrade() -> None:
    op.drop_index(
        "ix_business_data_sources_connection_id", table_name="business_data_sources"
    )
    op.drop_column("business_data_sources", "connection_id")
    op.drop_index(
        "ix_platform_data_connections_company_id",
        table_name="platform_data_connections",
    )
    op.drop_table("platform_data_connections")
