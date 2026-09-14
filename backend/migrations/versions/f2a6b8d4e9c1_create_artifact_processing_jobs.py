"""create durable artifact processing jobs

Revision ID: f2a6b8d4e9c1
Revises: e7b3c9d1a4f6
Create Date: 2026-09-13
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f2a6b8d4e9c1"
down_revision: Union[str, Sequence[str], None] = "e7b3c9d1a4f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLE = "artifact_processing_jobs"
_SCOPE = "NULLIF(current_setting('app.company_id', true), '')::integer"


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("artifact_version_id", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'queued'"),
            nullable=False,
        ),
        sa.Column(
            "attempt_generation",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "retry_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "max_attempts",
            sa.Integer(),
            server_default=sa.text("3"),
            nullable=False,
        ),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("execution_id", sa.String(length=36), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column("trace_request_id", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("stage IN ('scan', 'parse')", name="ck_artifact_processing_job_stage"),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'rejected', 'failed')",
            name="ck_artifact_processing_job_status",
        ),
        sa.CheckConstraint(
            "attempt_generation >= 0",
            name="ck_artifact_processing_job_attempt_generation",
        ),
        sa.CheckConstraint(
            "retry_count >= 0 AND max_attempts > 0 AND retry_count <= max_attempts",
            name="ck_artifact_processing_job_retry_limits",
        ),
        sa.CheckConstraint(
            "length(btrim(trace_request_id)) BETWEEN 1 AND 128",
            name="ck_artifact_processing_job_trace_request_id",
        ),
        sa.CheckConstraint(
            "last_error_code IS NULL OR length(btrim(last_error_code)) BETWEEN 1 AND 64",
            name="ck_artifact_processing_job_last_error_code",
        ),
        sa.CheckConstraint(
            """
            (status = 'queued'
                AND execution_id IS NULL
                AND lease_expires_at IS NULL
                AND finished_at IS NULL)
            OR (status = 'running'
                AND attempt_generation > 0
                AND execution_id IS NOT NULL
                AND lease_expires_at IS NOT NULL
                AND finished_at IS NULL)
            OR (status = 'succeeded'
                AND execution_id IS NULL
                AND lease_expires_at IS NULL
                AND finished_at IS NOT NULL
                AND last_error_code IS NULL)
            OR (status IN ('rejected', 'failed')
                AND execution_id IS NULL
                AND lease_expires_at IS NULL
                AND finished_at IS NOT NULL
                AND last_error_code IS NOT NULL)
            """,
            name="ck_artifact_processing_job_state_fields",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["artifact_version_id"], ["input_artifact_versions.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "artifact_version_id",
            "stage",
            name="uq_artifact_processing_job_version_stage",
        ),
    )
    for column in (
        "company_id",
        "artifact_version_id",
        "status",
        "available_at",
    ):
        op.create_index(f"ix_{_TABLE}_{column}", _TABLE, [column])

    op.execute(f"ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {_TABLE} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY artifact_processing_jobs_tenant_scope
        ON {_TABLE}
        USING (company_id = {_SCOPE})
        WITH CHECK (company_id = {_SCOPE})
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY artifact_processing_jobs_tenant_scope ON " + _TABLE)
    op.drop_table(_TABLE)
