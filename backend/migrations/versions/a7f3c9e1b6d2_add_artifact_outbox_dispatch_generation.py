"""add artifact outbox dispatch generation

Revision ID: a7f3c9e1b6d2
Revises: e5f8a2b9c3d6
Create Date: 2026-09-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a7f3c9e1b6d2"
down_revision: str | Sequence[str] | None = "e5f8a2b9c3d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_TABLE = "artifact_processing_outbox_events"
_OLD_UNIQUE = "uq_artifact_processing_outbox_job_event_type"
_NEW_UNIQUE = "uq_artifact_processing_outbox_job_dispatch_generation"
_CHECK = "ck_artifact_processing_outbox_dispatch_generation"


def upgrade() -> None:
    op.add_column(
        _TABLE,
        sa.Column("dispatch_generation", sa.Integer(), nullable=True),
    )
    op.execute(
        sa.text(
            f"UPDATE {_TABLE} SET dispatch_generation = 1 "
            "WHERE dispatch_generation IS NULL"
        )
    )
    op.alter_column(
        _TABLE,
        "dispatch_generation",
        existing_type=sa.Integer(),
        nullable=False,
        server_default=sa.text("1"),
    )
    op.create_check_constraint(_CHECK, _TABLE, "dispatch_generation > 0")
    op.drop_constraint(_OLD_UNIQUE, _TABLE, type_="unique")
    op.create_unique_constraint(
        _NEW_UNIQUE,
        _TABLE,
        ["job_id", "dispatch_generation"],
    )


def downgrade() -> None:
    duplicate_job_id = (
        op.get_bind()
        .execute(
            sa.text(
                f"SELECT job_id FROM {_TABLE} GROUP BY job_id "
                "HAVING COUNT(*) > 1 LIMIT 1"
            )
        )
        .scalar_one_or_none()
    )
    if duplicate_job_id is not None:
        raise RuntimeError(
            "cannot remove dispatch_generation while a job has multiple dispatch events"
        )

    op.drop_constraint(_NEW_UNIQUE, _TABLE, type_="unique")
    op.drop_constraint(_CHECK, _TABLE, type_="check")
    op.create_unique_constraint(_OLD_UNIQUE, _TABLE, ["job_id", "event_type"])
    op.drop_column(_TABLE, "dispatch_generation")
