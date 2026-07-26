"""add membership applications, invitations, and hashed API keys

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
"""

from __future__ import annotations

import hashlib

from alembic import op
import sqlalchemy as sa


revision = "c8d9e0f1a2b3"
down_revision = "b7c8d9e0f1a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("api_key_hash", sa.String(length=64), nullable=True)
    )
    users = sa.table(
        "users",
        sa.column("id", sa.Integer),
        sa.column("api_key", sa.String),
        sa.column("api_key_hash", sa.String),
    )
    bind = op.get_bind()
    rows = bind.execute(sa.select(users.c.id, users.c.api_key)).all()
    for user_id, api_key in rows:
        digest = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
        bind.execute(
            users.update().where(users.c.id == user_id).values(api_key_hash=digest)
        )
    op.alter_column("users", "api_key_hash", nullable=False)
    op.drop_index("ix_users_api_key", table_name="users")
    op.drop_column("users", "api_key")
    op.create_index("ix_users_api_key_hash", "users", ["api_key_hash"], unique=True)

    op.create_table(
        "company_invitations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("max_uses", sa.Integer(), nullable=False),
        sa.Column("used_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "max_uses > 0", name="company_invitations_max_uses_positive"
        ),
        sa.CheckConstraint(
            "used_count >= 0 AND used_count <= max_uses",
            name="company_invitations_used_count_range",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("code_hash", name="uq_company_invitations_code_hash"),
    )
    op.create_index(
        "ix_company_invitations_company_id", "company_invitations", ["company_id"]
    )

    op.create_table(
        "membership_applications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("invitation_id", sa.Integer(), nullable=False),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="pending"
        ),
        sa.Column("reviewed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="membership_applications_status_values",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["invitation_id"], ["company_invitations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("user_id", name="uq_membership_applications_user"),
    )
    op.create_index(
        "ix_membership_applications_user_id", "membership_applications", ["user_id"]
    )
    op.create_index(
        "ix_membership_applications_company_id",
        "membership_applications",
        ["company_id"],
    )


def downgrade() -> None:
    raise NotImplementedError("account lifecycle migration is irreversible")
