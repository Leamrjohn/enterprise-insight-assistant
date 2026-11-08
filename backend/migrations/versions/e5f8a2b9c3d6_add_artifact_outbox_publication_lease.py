"""add artifact outbox publication lease

Revision ID: e5f8a2b9c3d6
Revises: d4e7f1a8b2c5
Create Date: 2026-09-13
"""

from typing import Callable, Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e5f8a2b9c3d6"
down_revision: Union[str, Sequence[str], None] = "d4e7f1a8b2c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLE = "artifact_processing_outbox_events"
_STATE_CONSTRAINT = "ck_artifact_processing_outbox_state_fields"
_STATUS_CONSTRAINT = "ck_artifact_processing_outbox_status"
_GENERATION_CONSTRAINT = "ck_artifact_processing_outbox_publish_generation"


def _find_check_constraint(predicate: Callable[[str], bool]) -> str:
    matches = [
        constraint["name"]
        for constraint in sa.inspect(op.get_bind()).get_check_constraints(_TABLE)
        if constraint["name"] and predicate(str(constraint.get("sqltext", "")))
    ]
    if len(matches) != 1:
        raise RuntimeError(f"expected exactly one matching check constraint, got {matches}")
    return matches[0]


def _old_state_constraint() -> str:
    return _find_check_constraint(
        lambda sql: "published_at" in sql
        and "broker_message_id" in sql
        and "publish_generation" not in sql
    )


def _new_state_constraint() -> str:
    return _find_check_constraint(
        lambda sql: "published_at" in sql
        and "broker_message_id" in sql
        and "publish_generation" in sql
    )


def _status_constraint() -> str:
    return _find_check_constraint(
        lambda sql: "status" in sql
        and "pending" in sql
        and "published" in sql
        and "published_at" not in sql
    )


def upgrade() -> None:
    op.add_column(
        _TABLE,
        sa.Column(
            "publish_generation",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        _TABLE,
        sa.Column("publish_execution_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        _TABLE,
        sa.Column("publish_lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        sa.text(
            f"UPDATE {_TABLE} SET publish_generation = 1 "
            "WHERE status = 'published'"
        )
    )
    op.drop_constraint(op.f(_old_state_constraint()), _TABLE, type_="check")
    op.drop_constraint(op.f(_status_constraint()), _TABLE, type_="check")
    op.create_check_constraint(
        _STATUS_CONSTRAINT,
        _TABLE,
        "status IN ('pending', 'publishing', 'published')",
    )
    op.create_check_constraint(
        _GENERATION_CONSTRAINT,
        _TABLE,
        "publish_generation >= 0",
    )
    op.create_check_constraint(
        _STATE_CONSTRAINT,
        _TABLE,
        """
        (status = 'pending'
            AND publish_execution_id IS NULL
            AND publish_lease_expires_at IS NULL
            AND published_at IS NULL
            AND broker_message_id IS NULL)
        OR (status = 'publishing'
            AND publish_generation > 0
            AND length(btrim(publish_execution_id)) BETWEEN 1 AND 36
            AND publish_lease_expires_at IS NOT NULL
            AND published_at IS NULL
            AND broker_message_id IS NULL
            AND last_error IS NULL)
        OR (status = 'published'
            AND publish_generation > 0
            AND publish_execution_id IS NULL
            AND publish_lease_expires_at IS NULL
            AND published_at IS NOT NULL
            AND length(btrim(broker_message_id)) BETWEEN 1 AND 255
            AND last_error IS NULL)
        """,
    )


def downgrade() -> None:
    publishing_count = op.get_bind().execute(
        sa.text(f"SELECT COUNT(*) FROM {_TABLE} WHERE status = 'publishing'")
    ).scalar_one()
    if publishing_count:
        raise RuntimeError(
            "cannot remove publication lease while artifact outbox events are publishing"
        )

    op.drop_constraint(op.f(_new_state_constraint()), _TABLE, type_="check")
    op.drop_constraint(op.f(_status_constraint()), _TABLE, type_="check")
    op.drop_constraint(
        op.f(
            _find_check_constraint(
                lambda sql: "publish_generation" in sql and ">= 0" in sql
            )
        ),
        _TABLE,
        type_="check",
    )
    op.create_check_constraint(
        _STATUS_CONSTRAINT,
        _TABLE,
        "status IN ('pending', 'published')",
    )
    op.create_check_constraint(
        _STATE_CONSTRAINT,
        _TABLE,
        """
        (status = 'pending'
            AND published_at IS NULL
            AND broker_message_id IS NULL)
        OR (status = 'published'
            AND published_at IS NOT NULL
            AND length(btrim(broker_message_id)) BETWEEN 1 AND 255)
        """,
    )
    op.drop_column(_TABLE, "publish_lease_expires_at")
    op.drop_column(_TABLE, "publish_execution_id")
    op.drop_column(_TABLE, "publish_generation")
