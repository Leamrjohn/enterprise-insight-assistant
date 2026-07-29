"""enforce tenant scope for documents and pgvector chunks

Revision ID: d1e2f3a4b5c6
Revises: c0d1e2f3a4b5
"""

from alembic import op
import sqlalchemy as sa


revision = "d1e2f3a4b5c6"
down_revision = "c0d1e2f3a4b5"
branch_labels = None
depends_on = None


_SCOPE = "NULLIF(current_setting('app.company_id', true), '')::integer"


def upgrade() -> None:
    # Historical documents predate company membership.  Infer only from an
    # approved, unique membership; refusing ambiguous records is safer than
    # assigning their vectors to an arbitrary tenant.
    op.execute(
        """
        UPDATE documents AS d
        SET company_id = cm.company_id
        FROM company_members AS cm
        WHERE d.company_id IS NULL
          AND cm.user_id = d.uploaded_by_user_id
          AND cm.status = 'approved'
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM documents WHERE company_id IS NULL) THEN
                RAISE EXCEPTION
                    'Cannot enable tenant RLS: documents without an approved company remain';
            END IF;
        END $$;
        """
    )

    op.alter_column("documents", "company_id", nullable=False)
    op.execute(
        """
        DO $$
        DECLARE foreign_key_name text;
        BEGIN
            SELECT con.conname
            INTO foreign_key_name
            FROM pg_constraint AS con
            JOIN pg_class AS rel ON rel.oid = con.conrelid
            JOIN pg_attribute AS attr
              ON attr.attrelid = rel.oid AND attr.attnum = ANY(con.conkey)
            WHERE rel.relname = 'documents'
              AND con.contype = 'f'
              AND attr.attname = 'company_id';

            IF foreign_key_name IS NOT NULL THEN
                EXECUTE format(
                    'ALTER TABLE documents DROP CONSTRAINT %I', foreign_key_name
                );
            END IF;
        END $$;
        """
    )
    op.create_foreign_key(
        "documents_company_id_fkey",
        "documents",
        "companies",
        ["company_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.add_column(
        "document_chunks",
        sa.Column("company_id", sa.Integer(), nullable=True),
    )
    op.execute(
        """
        UPDATE document_chunks AS dc
        SET company_id = d.company_id
        FROM documents AS d
        WHERE d.id = dc.document_id
        """
    )
    op.alter_column("document_chunks", "company_id", nullable=False)
    op.create_foreign_key(
        "document_chunks_company_id_fkey",
        "document_chunks",
        "companies",
        ["company_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_document_chunks_company_document",
        "document_chunks",
        ["company_id", "document_id"],
        unique=False,
    )

    for table in ("documents", "document_chunks"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        # The current deployment originally used agent_app as table owner.
        # FORCE also protects that upgraded deployment; superusers/BYPASSRLS
        # roles remain intentionally restricted to bootstrap administration.
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {table}_tenant_scope ON {table}
            USING (company_id = {_SCOPE})
            WITH CHECK (company_id = {_SCOPE})
            """
        )

    # Cold deployments run Alembic as agent_migrator.  The API/Workers use a
    # separate non-owner login and receive only data-plane privileges.
    op.execute("GRANT USAGE ON SCHEMA public TO agent_app")
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO agent_app"
    )
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO agent_app")
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO agent_app"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "GRANT USAGE, SELECT ON SEQUENCES TO agent_app"
    )


def downgrade() -> None:
    for table in ("documents", "document_chunks"):
        op.execute(f"DROP POLICY {table}_tenant_scope ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    op.drop_index("ix_document_chunks_company_document", table_name="document_chunks")
    op.drop_constraint(
        "document_chunks_company_id_fkey", "document_chunks", type_="foreignkey"
    )
    op.drop_column("document_chunks", "company_id")

    op.drop_constraint("documents_company_id_fkey", "documents", type_="foreignkey")
    op.create_foreign_key(
        "documents_company_id_fkey",
        "documents",
        "companies",
        ["company_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.alter_column("documents", "company_id", nullable=True)
