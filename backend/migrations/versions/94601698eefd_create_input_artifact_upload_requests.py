"""create input artifact upload requests

Revision ID: 94601698eefd
Revises: 7e9b1c3d5f7a
Create Date: 2026-09-11 09:32:40.466648

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "94601698eefd"
down_revision: Union[str, Sequence[str], None] = "7e9b1c3d5f7a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "input_artifact_upload_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("submitted_by_user_id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=True),
        sa.Column("artifact_version_id", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("trace_request_id", sa.String(length=128), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('receiving', 'completed', 'rejected', 'failed')",
            name="ck_input_artifact_upload_requests_status",
        ),
        sa.CheckConstraint(
            """
            (status = 'receiving'
                AND payload_hash IS NULL
                AND artifact_version_id IS NULL
                AND error_code IS NULL
                AND lease_expires_at IS NOT NULL
                AND finished_at IS NULL)
            OR (status = 'completed'
                AND payload_hash IS NOT NULL
                AND artifact_version_id IS NOT NULL
                AND error_code IS NULL
                AND lease_expires_at IS NULL
                AND finished_at IS NOT NULL)
            OR (status IN ('rejected', 'failed')
                AND artifact_version_id IS NULL
                AND error_code IS NOT NULL
                AND lease_expires_at IS NULL
                AND finished_at IS NOT NULL)
            """,
            name="ck_input_upload_request_state_fields",
        ),
        sa.CheckConstraint(
            "payload_hash IS NULL OR payload_hash ~ '^[0-9a-f]{64}$'",
            name="ck_payload_hash",
        ),
        sa.CheckConstraint(
            "length(btrim(idempotency_key)) BETWEEN 1 AND 128",
            name="ck_input_upload_request_idempotency_key",
        ),
        sa.CheckConstraint(
            "error_code IS NULL OR length(btrim(error_code)) BETWEEN 1 AND 64",
            name="ck_input_upload_request_error_code",
        ),
        sa.CheckConstraint(
            "length(btrim(trace_request_id)) BETWEEN 1 AND 128",
            name="ck_input_upload_request_trace_request_id",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["submitted_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["conversations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["artifact_version_id"],
            ["input_artifact_versions.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "submitted_by_user_id",
            "conversation_id",
            "idempotency_key",
            name="uq_input_upload_request_scope_key",
        ),
    )
    for column in (
        "company_id",
        "submitted_by_user_id",
        "conversation_id",
        "artifact_version_id",
        "trace_request_id",
    ):
        op.create_index(
            f"ix_input_artifact_upload_requests_{column}",
            "input_artifact_upload_requests",
            [column],
        )

    scope = "NULLIF(current_setting('app.company_id', true), '')::integer"
    op.execute("ALTER TABLE input_artifact_upload_requests ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE input_artifact_upload_requests FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY input_artifact_upload_requests_tenant_scope
        ON input_artifact_upload_requests
        USING (company_id = {scope})
        WITH CHECK (company_id = {scope})
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY input_artifact_upload_requests_tenant_scope "
        "ON input_artifact_upload_requests"
    )
    op.drop_table("input_artifact_upload_requests")
