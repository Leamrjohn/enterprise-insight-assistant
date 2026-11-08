"""add immutable input upload request fingerprint

Revision ID: c4f7e1a9b2d6
Revises: b3a6e1c4d8f2
"""

import hashlib
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4f7e1a9b2d6"
down_revision: Union[str, Sequence[str], None] = "b3a6e1c4d8f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLE_NAME = "input_artifact_upload_requests"
_CONSTRAINT_NAME = "ck_input_upload_request_request_fingerprint"


def _legacy_fingerprint(request_id: int) -> str:
    """Prevent a legacy request from being replayed as a new request."""
    value = f"legacy-input-upload-request:{request_id}".encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def upgrade() -> None:
    op.add_column(
        _TABLE_NAME,
        sa.Column("request_fingerprint", sa.String(length=64), nullable=True),
    )

    connection = op.get_bind()
    request_ids = connection.execute(
        sa.text(f"SELECT id FROM {_TABLE_NAME} ORDER BY id")
    ).scalars()
    for request_id in request_ids:
        connection.execute(
            sa.text(
                f"UPDATE {_TABLE_NAME} "
                "SET request_fingerprint = :fingerprint "
                "WHERE id = :request_id"
            ),
            {
                "request_id": request_id,
                "fingerprint": _legacy_fingerprint(request_id),
            },
        )

    op.alter_column(_TABLE_NAME, "request_fingerprint", nullable=False)
    op.create_check_constraint(
        _CONSTRAINT_NAME,
        _TABLE_NAME,
        "request_fingerprint ~ '^[0-9a-f]{64}$'",
    )


def downgrade() -> None:
    op.drop_constraint(_CONSTRAINT_NAME, _TABLE_NAME, type_="check")
    op.drop_column(_TABLE_NAME, "request_fingerprint")
