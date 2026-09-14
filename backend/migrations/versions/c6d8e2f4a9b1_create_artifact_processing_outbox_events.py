"""create artifact processing outbox events

Revision ID: c6d8e2f4a9b1
Revises: f2a6b8d4e9c1
Create Date: 2026-09-13
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c6d8e2f4a9b1"
down_revision: Union[str, Sequence[str], None] = "f2a6b8d4e9c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLE = "artifact_processing_outbox_events"
_SCOPE = "NULLIF(current_setting('app.company_id', true), '')::integer"


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column(
            "publish_attempt_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("last_error", sa.String(length=2000), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trace_request_id", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "event_type = 'artifact_processing_job.created'",
            name="ck_artifact_processing_outbox_event_type",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'published')",
            name="ck_artifact_processing_outbox_status",
        ),
        sa.CheckConstraint(
            "publish_attempt_count >= 0",
            name="ck_artifact_processing_outbox_publish_attempt_count",
        ),
        sa.CheckConstraint(
            "(status = 'pending' AND published_at IS NULL) OR "
            "(status = 'published' AND published_at IS NOT NULL)",
            name="ck_artifact_processing_outbox_state_fields",
        ),
        sa.CheckConstraint(
            "last_error IS NULL OR length(btrim(last_error)) BETWEEN 1 AND 2000",
            name="ck_artifact_processing_outbox_last_error",
        ),
        sa.CheckConstraint(
            "length(btrim(trace_request_id)) BETWEEN 1 AND 128",
            name="ck_artifact_processing_outbox_trace_request_id",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["job_id"], ["artifact_processing_jobs.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "job_id",
            "event_type",
            name="uq_artifact_processing_outbox_job_event_type",
        ),
    )
    for column in ("company_id", "job_id", "status"):
        op.create_index(f"ix_{_TABLE}_{column}", _TABLE, [column])

    op.execute(f"ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {_TABLE} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY artifact_processing_outbox_events_tenant_scope
        ON {_TABLE}
        USING (company_id = {_SCOPE})
        WITH CHECK (company_id = {_SCOPE})
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY artifact_processing_outbox_events_tenant_scope ON " + _TABLE)
    op.drop_table(_TABLE)
