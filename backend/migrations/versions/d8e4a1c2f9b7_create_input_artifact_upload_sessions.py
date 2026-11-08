"""create direct upload sessions for input artifacts

Revision ID: d8e4a1c2f9b7
Revises: c4f7e1a9b2d6
Create Date: 2026-09-13
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d8e4a1c2f9b7"
down_revision: Union[str, Sequence[str], None] = "c4f7e1a9b2d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLE = "input_artifact_upload_sessions"
_SCOPE = "NULLIF(current_setting('app.company_id', true), '')::integer"


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.String(length=36), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("submitted_by_user_id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("client_filename", sa.String(length=255), nullable=False),
        sa.Column("client_reported_byte_size", sa.BigInteger(), nullable=False),
        sa.Column("client_reported_mime_type", sa.String(length=255), nullable=True),
        sa.Column("upload_policy_version", sa.String(length=64), nullable=False),
        sa.Column("storage_provider", sa.String(length=64), nullable=False),
        sa.Column("staging_object_key", sa.String(length=512), nullable=False),
        sa.Column("storage_provider_upload_id", sa.String(length=255), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'awaiting_upload'"),
            nullable=False,
        ),
        sa.Column(
            "finalization_generation",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("finalization_execution_id", sa.String(length=36), nullable=True),
        sa.Column("finalization_lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("upload_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("storage_verified_byte_size", sa.BigInteger(), nullable=True),
        sa.Column("storage_verified_sha256", sa.String(length=64), nullable=True),
        sa.Column("artifact_version_id", sa.Integer(), nullable=True),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.Column("trace_request_id", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('awaiting_upload', 'finalizing', 'completed', 'rejected', 'expired', 'failed')",
            name="ck_input_upload_session_status",
        ),
        sa.CheckConstraint(
            "client_reported_byte_size >= 0",
            name="ck_input_upload_session_client_reported_byte_size",
        ),
        sa.CheckConstraint(
            "request_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_input_upload_session_request_fingerprint",
        ),
        sa.CheckConstraint(
            "storage_verified_sha256 IS NULL OR storage_verified_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_input_upload_session_storage_verified_sha256",
        ),
        sa.CheckConstraint(
            "finalization_generation >= 0",
            name="ck_input_upload_session_finalization_generation",
        ),
        sa.CheckConstraint(
            "length(btrim(idempotency_key)) BETWEEN 1 AND 128",
            name="ck_input_upload_session_idempotency_key",
        ),
        sa.CheckConstraint(
            "length(btrim(client_filename)) BETWEEN 1 AND 255",
            name="ck_input_upload_session_client_filename",
        ),
        sa.CheckConstraint(
            "length(btrim(staging_object_key)) BETWEEN 1 AND 512",
            name="ck_input_upload_session_staging_object_key",
        ),
        sa.CheckConstraint(
            "length(btrim(upload_policy_version)) BETWEEN 1 AND 64",
            name="ck_input_upload_session_upload_policy_version",
        ),
        sa.CheckConstraint(
            "failure_code IS NULL OR length(btrim(failure_code)) BETWEEN 1 AND 64",
            name="ck_input_upload_session_failure_code",
        ),
        sa.CheckConstraint(
            "length(btrim(trace_request_id)) BETWEEN 1 AND 128",
            name="ck_input_upload_session_trace_request_id",
        ),
        sa.CheckConstraint(
            """
            (status = 'awaiting_upload'
                AND finalization_generation = 0
                AND finalization_execution_id IS NULL
                AND finalization_lease_expires_at IS NULL
                AND storage_verified_byte_size IS NULL
                AND storage_verified_sha256 IS NULL
                AND artifact_version_id IS NULL
                AND failure_code IS NULL
                AND finished_at IS NULL)
            OR (status = 'finalizing'
                AND finalization_generation > 0
                AND finalization_execution_id IS NOT NULL
                AND finalization_lease_expires_at IS NOT NULL
                AND storage_verified_byte_size IS NULL
                AND storage_verified_sha256 IS NULL
                AND artifact_version_id IS NULL
                AND failure_code IS NULL
                AND finished_at IS NULL)
            OR (status = 'completed'
                AND finalization_generation > 0
                AND finalization_execution_id IS NULL
                AND finalization_lease_expires_at IS NULL
                AND storage_verified_byte_size IS NOT NULL
                AND storage_verified_sha256 IS NOT NULL
                AND artifact_version_id IS NOT NULL
                AND failure_code IS NULL
                AND finished_at IS NOT NULL)
            OR (status IN ('rejected', 'expired', 'failed')
                AND finalization_execution_id IS NULL
                AND finalization_lease_expires_at IS NULL
                AND storage_verified_byte_size IS NULL
                AND storage_verified_sha256 IS NULL
                AND artifact_version_id IS NULL
                AND failure_code IS NOT NULL
                AND finished_at IS NOT NULL)
            """,
            name="ck_input_upload_session_state_fields",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["submitted_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["artifact_version_id"], ["input_artifact_versions.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id", name="uq_input_upload_session_public_id"),
        sa.UniqueConstraint(
            "company_id",
            "submitted_by_user_id",
            "conversation_id",
            "idempotency_key",
            name="uq_input_upload_session_scope_key",
        ),
        sa.UniqueConstraint(
            "staging_object_key",
            name="uq_input_upload_session_staging_object_key",
        ),
    )
    for column in (
        "company_id",
        "submitted_by_user_id",
        "conversation_id",
        "status",
        "upload_expires_at",
        "artifact_version_id",
        "trace_request_id",
    ):
        op.create_index(f"ix_{_TABLE}_{column}", _TABLE, [column])

    op.execute(f"ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {_TABLE} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY input_artifact_upload_sessions_tenant_scope
        ON {_TABLE}
        USING (company_id = {_SCOPE})
        WITH CHECK (company_id = {_SCOPE})
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY input_artifact_upload_sessions_tenant_scope "
        f"ON {_TABLE}"
    )
    op.drop_table(_TABLE)
