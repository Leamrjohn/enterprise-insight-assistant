from typing import BinaryIO

from app.core.settings import Settings
from app.modules.input_artifacts.models import InputArtifactVersion
from app.modules.input_artifacts.storage import (
    discard_stored_input_artifact_file,
    store_input_artifact_file,
)
from app.modules.input_artifacts.versions import create_received_input_artifact_version
from sqlalchemy.orm import Session


def ingest_received_input_artifact(
    db: Session,
    *,
    company_id: int,
    uploaded_by_user_id: int,
    kind: str,
    file_stream: BinaryIO,
    original_filename: str | None,
    settings: Settings,
    declared_mime_type: str | None = None,
) -> InputArtifactVersion:
    """Store one untrusted file, then atomically create its received database version.

    The filesystem cannot join the database transaction. If database persistence
    fails, this function compensates by deleting only the file it just created.
    """
    stored_file = store_input_artifact_file(
        file_stream=file_stream,
        original_filename=original_filename,
        settings=settings,
    )
    try:
        return create_received_input_artifact_version(
            db,
            company_id=company_id,
            uploaded_by_user_id=uploaded_by_user_id,
            kind=kind,
            original_filename=stored_file.original_filename,
            raw_object_key=stored_file.raw_object_key,
            byte_size=stored_file.byte_size,
            sha256=stored_file.sha256,
            declared_mime_type=declared_mime_type,
        )
    except Exception:
        discard_stored_input_artifact_file(stored_file, settings=settings)
        raise
