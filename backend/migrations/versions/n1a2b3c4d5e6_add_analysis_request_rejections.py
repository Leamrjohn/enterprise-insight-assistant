"""persist denied analysis submissions for scoped evaluation

Revision ID: n1a2b3c4d5e6
Revises: e8f9a0b1c2d3
Create Date: 2026-10-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "n1a2b3c4d5e6"
down_revision: str | Sequence[str] | None = "e8f9a0b1c2d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_TABLE = "analysis_request_rejections"
_SCOPE = "NULLIF(current_setting('app.company_id', true), '')::integer"


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("status_code BETWEEN 400 AND 499", name="client_error_status"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("request_id", name="uq_analysis_request_rejections_request_id"),
    )
    op.create_index("ix_analysis_request_rejections_company_id", _TABLE, ["company_id"])
    op.execute(f"ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {_TABLE} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY analysis_request_rejections_tenant_scope
        ON {_TABLE}
        USING (company_id = {_SCOPE})
        WITH CHECK (company_id = {_SCOPE})
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY analysis_request_rejections_tenant_scope ON " + _TABLE)
    op.execute(f"ALTER TABLE {_TABLE} NO FORCE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {_TABLE} DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_analysis_request_rejections_company_id", table_name=_TABLE)
    op.drop_table(_TABLE)
