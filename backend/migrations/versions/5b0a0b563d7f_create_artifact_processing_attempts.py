"""create artifact processing attempts

Revision ID: 5b0a0b563d7f
Revises: 13d539ca4441
Create Date: 2026-09-11 01:34:53.166253

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5b0a0b563d7f'
down_revision: Union[str, Sequence[str], None] = '13d539ca4441'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "artifact_processing_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("artifact_version_id", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("processor_name", sa.String(length=64), nullable=False),
        sa.Column("processor_version", sa.String(length=64), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("retry_disposition", sa.String(length=32), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trace_id", sa.String(length=128), nullable=False),
        sa.CheckConstraint(
            "status IS NOT NULL AND status IN ('running','succeeded','failed','rejected')",
            name="status_values",
        ),
        sa.CheckConstraint("stage IN ('scan','parse')", name="stage_values"),
        sa.CheckConstraint("attempt_number > 0", name="attempt_number_positive"),
        sa.CheckConstraint(
            "retry_disposition IS NULL OR retry_disposition IN "
            "('scheduled','not_retryable','exhausted')",
            name="retry_disposition_values",
        ),
        sa.CheckConstraint(
            "COALESCE("
            "(retry_disposition IS NULL AND next_retry_at IS NULL)"
            " OR (retry_disposition = 'scheduled' AND next_retry_at IS NOT NULL)"
            " OR (retry_disposition IN ('not_retryable', 'exhausted') "
            "AND next_retry_at IS NULL), FALSE)",
            name="retry_schedule_matches_disposition",
        ),
        sa.CheckConstraint(
            "(status = 'running' AND finished_at IS NULL AND error_code IS NULL "
            "AND retry_disposition IS NULL) "
            "OR (status = 'succeeded' AND finished_at IS NOT NULL "
            "AND error_code IS NULL AND retry_disposition IS NULL) "
            "OR (status = 'failed' AND finished_at IS NOT NULL "
            "AND error_code IS NOT NULL AND retry_disposition IS NOT NULL "
            "AND retry_disposition IN ('scheduled','not_retryable','exhausted')) "
            "OR (status = 'rejected' AND finished_at IS NOT NULL "
            "AND error_code IS NOT NULL AND retry_disposition IS NULL "
            "AND stage = 'scan')",
            name="status_fields_match_status",
        ),
        sa.UniqueConstraint(
            "artifact_version_id",
            "stage",
            "attempt_number",
            name="uq_artifact_version_id_stage_attempt_number",
        ),
        sa.ForeignKeyConstraint(
            ["artifact_version_id"],
            ["input_artifact_versions.id"],
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_artifact_processing_attempts_artifact_version_id",
        "artifact_processing_attempts",
        ["artifact_version_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_artifact_processing_attempts_artifact_version_id",
        table_name="artifact_processing_attempts",
    )
    op.drop_table("artifact_processing_attempts")
