import errno
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

from app.core.exceptions import (
    DocumentTooLargeError,
    EmptyDocumentError,
    InsufficientStorageError,
    InvalidDocumentNameError,
    UnsupportedDocumentTypeError,
)
from app.core.settings import Settings


@dataclass(frozen=True, slots=True)
class StoredDocumentFile:
    original_name: str
    stored_name: str
    relative_path: str
    absolute_path: Path
    extension: str
    size_bytes: int
    sha256: str


def _validate_document_name(
    original_name: str | None, allowed_extensions: list[str]
) -> tuple[str, str]:
    if not original_name:
        raise InvalidDocumentNameError("Original name cannot be None")
    normalized_name = original_name.replace("\\", "/")
    safe_name = normalized_name.split("/")[-1].strip()

    if not safe_name or safe_name in {".", ".."}:
        raise InvalidDocumentNameError(f"Invalid document name: '{original_name}'")

    extension = Path(safe_name).suffix.lower()
    normalized_extension = {item.lower() for item in allowed_extensions}

    if extension not in normalized_extension:
        raise UnsupportedDocumentTypeError(
            f"Unsupported document type: '{extension}'. "
        )
    return safe_name, extension


def save_document_file(
    file_stream: BinaryIO,
    original_name: str | None,
    settings: Settings,
) -> StoredDocumentFile:
    safe_name, extension = _validate_document_name(
        original_name, settings.allowed_document_extensions
    )

    try:
        settings.upload_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        if exc.errno == errno.ENOSPC:
            raise InsufficientStorageError("application storage is full") from exc
        raise
    stored_name = f"{uuid4().hex}{extension}"
    absolute_path = settings.upload_dir / stored_name
    relative_path = absolute_path.relative_to(settings.storage_dir).as_posix()

    max_size_bytes = settings.max_upload_size_mb * 1024 * 1024
    size_bytes = 0
    sha256_hash = hashlib.sha256()

    file_stream.seek(0)

    file_created = False
    try:
        with absolute_path.open("xb") as target_file:
            file_created = True
            while True:
                chunk = file_stream.read(settings.upload_chunk_size_bytes)
                if not chunk:
                    break
                size_bytes += len(chunk)
                if size_bytes > max_size_bytes:
                    raise DocumentTooLargeError(
                        f"Document exceeds maximum size of {settings.max_upload_size_mb} MB"
                    )
                sha256_hash.update(chunk)
                target_file.write(chunk)

        if size_bytes == 0:
            raise EmptyDocumentError("Document file is empty")
    except OSError as exc:
        if file_created:
            absolute_path.unlink(missing_ok=True)
        if exc.errno == errno.ENOSPC:
            raise InsufficientStorageError("application storage is full") from exc
        raise
    except Exception:
        if file_created:
            absolute_path.unlink(missing_ok=True)
        raise
    return StoredDocumentFile(
        original_name=safe_name,
        stored_name=stored_name,
        relative_path=relative_path,
        absolute_path=absolute_path,
        extension=extension,
        size_bytes=size_bytes,
        sha256=sha256_hash.hexdigest(),
    )
