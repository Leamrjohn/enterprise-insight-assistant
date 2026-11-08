"""harden artifact processing outbox delivery

Revision ID: d4e7f1a8b2c5
Revises: c6d8e2f4a9b1
Create Date: 2026-09-13
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4e7f1a8b2c5"
down_revision: Union[str, Sequence[str], None] = "c6d8e2f4a9b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_JOBS_TABLE = "artifact_processing_jobs"
_OUTBOX_TABLE = "artifact_processing_outbox_events"
_JOB_SCOPE_UNIQUE = "uq_artifact_processing_job_id_with_company_id"
_JOB_COMPANY_FOREIGN_KEY = "fk_artifact_processing_outbox_event_job_company"
_OUTBOX_STATE_CONSTRAINT = "ck_artifact_processing_outbox_state_fields"


def _find_single_job_foreign_key() -> str:
    inspector = sa.inspect(op.get_bind())
    matches = [
        foreign_key["name"]
        for foreign_key in inspector.get_foreign_keys(_OUTBOX_TABLE)
        if foreign_key["constrained_columns"] == ["job_id"]
        and foreign_key["referred_table"] == _JOBS_TABLE
    ]
    if len(matches) != 1 or not matches[0]:
        raise RuntimeError("expected exactly one legacy outbox job foreign key")
    return matches[0]


def _find_outbox_state_constraint() -> str:
    inspector = sa.inspect(op.get_bind())
    matches = [
        constraint["name"]
        for constraint in inspector.get_check_constraints(_OUTBOX_TABLE)
        if "published_at" in str(constraint.get("sqltext", ""))
    ]
    if len(matches) != 1 or not matches[0]:
        raise RuntimeError("expected exactly one legacy outbox state constraint")
    return matches[0]


def upgrade() -> None:
    connection = op.get_bind()
    published_count = connection.execute(
        sa.text(
            f"SELECT COUNT(*) FROM {_OUTBOX_TABLE} "
            "WHERE status = 'published'"
        )
    ).scalar_one()
    if published_count:
        raise RuntimeError(
            "cannot add required broker message identity while published artifact "
            "outbox events exist; reconcile them before this migration"
        )

    op.add_column(
        _OUTBOX_TABLE,
        sa.Column("broker_message_id", sa.String(length=255), nullable=True),
    )
    op.create_unique_constraint(
        _JOB_SCOPE_UNIQUE,
        _JOBS_TABLE,
        ["id", "company_id"],
    )
    op.drop_constraint(
        op.f(_find_single_job_foreign_key()),
        _OUTBOX_TABLE,
        type_="foreignkey",
    )
    op.create_foreign_key(
        _JOB_COMPANY_FOREIGN_KEY,
        _OUTBOX_TABLE,
        _JOBS_TABLE,
        ["company_id", "job_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint(
        op.f(_find_outbox_state_constraint()),
        _OUTBOX_TABLE,
        type_="check",
    )
    op.create_check_constraint(
        _OUTBOX_STATE_CONSTRAINT,
        _OUTBOX_TABLE,
        """
        (status = 'pending'
            AND published_at IS NULL
            AND broker_message_id IS NULL)
        OR (status = 'published'
            AND published_at IS NOT NULL
            AND length(btrim(broker_message_id)) BETWEEN 1 AND 255)
        """,
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f(_find_outbox_state_constraint()),
        _OUTBOX_TABLE,
        type_="check",
    )
    op.create_check_constraint(
        _OUTBOX_STATE_CONSTRAINT,
        _OUTBOX_TABLE,
        """
        (status = 'pending' AND published_at IS NULL)
        OR (status = 'published' AND published_at IS NOT NULL)
        """,
    )
    op.drop_constraint(
        _JOB_COMPANY_FOREIGN_KEY,
        _OUTBOX_TABLE,
        type_="foreignkey",
    )
    op.create_foreign_key(
        None,
        _OUTBOX_TABLE,
        _JOBS_TABLE,
        ["job_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint(_JOB_SCOPE_UNIQUE, _JOBS_TABLE, type_="unique")
    op.drop_column(_OUTBOX_TABLE, "broker_message_id")
