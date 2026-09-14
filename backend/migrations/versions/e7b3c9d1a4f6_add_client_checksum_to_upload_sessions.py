"""require client checksum for direct upload sessions

Revision ID: e7b3c9d1a4f6
Revises: d8e4a1c2f9b7
Create Date: 2026-09-13
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e7b3c9d1a4f6"
down_revision: Union[str, Sequence[str], None] = "d8e4a1c2f9b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLE = "input_artifact_upload_sessions"
_CONSTRAINT = "ck_input_upload_session_client_reported_sha256"


def upgrade() -> None:
    connection = op.get_bind()
    existing_sessions = connection.execute(
        sa.text(f"SELECT COUNT(*) FROM {_TABLE}")
    ).scalar_one()
    if existing_sessions:
        raise RuntimeError(
            "cannot add a required client checksum after upload sessions exist; "
            "reconcile or expire them before this migration"
        )

    op.add_column(
        _TABLE,
        sa.Column("client_reported_sha256", sa.String(length=64), nullable=False),
    )
    op.create_check_constraint(
        _CONSTRAINT,
        _TABLE,
        "client_reported_sha256 ~ '^[0-9a-f]{64}$'",
    )


def downgrade() -> None:
    op.drop_constraint(_CONSTRAINT, _TABLE, type_="check")
    op.drop_column(_TABLE, "client_reported_sha256")
