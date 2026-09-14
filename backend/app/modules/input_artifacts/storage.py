from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import BinaryIO, Literal
from uuid import uuid4

from regex import S

from app.core.exceptions import (
    EmptyInputArtifactError,
    InputArtifactTooLargeError,
    InvalidInputArtifactNameError,
    UnsupportedInputArtifactTypeError,
)
from app.core.settings import Settings


_ArtifactCategory = Literal["document", "table", "image"]
_EXTENSION_CATEGORIES: dict[str, _ArtifactCategory] = {
    ".txt": "document",
    ".md": "document",
    ".pdf": "document",
    ".csv": "table",
    ".xlsx": "table",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".webp": "image",
}


@dataclass(frozen=True, slots=True)
class StoredInputArtifactFile:
    original_filename: str
    raw_object_key: str
    absolute_path: Path
    byte_size: int
    sha256: str
    category: _ArtifactCategory


@dataclass(frozen=True, slots=True)
class InspectedInputArtifactFile:
    original_filename: str
    category: _ArtifactCategory
    byte_size: int
    sha256: str


@dataclass(frozen=True, slots=True)
class DeclaredInputArtifactUpload:
    """Untrusted browser metadata accepted before direct object upload."""

    original_filename: str
    category: _ArtifactCategory
    byte_size: int
    declared_mime_type: str | None
    client_reported_sha256: str


def discard_stored_input_artifact_file(
    stored_file: StoredInputArtifactFile,
    *,
    settings: Settings,
) -> None:
    """Remove a newly stored quarantine file during a failed ingest transaction."""
    quarantine_dir = settings.input_artifact_quarantine_dir.resolve()
    try:
        stored_file.absolute_path.resolve().relative_to(quarantine_dir)
    except ValueError as exc:
        raise RuntimeError(
            "refusing to delete a file outside the quarantine directory"
        ) from exc
    stored_file.absolute_path.unlink(missing_ok=True)


def normalize_input_artifact_filename(
    original_filename: str | None,
) -> tuple[str, str, _ArtifactCategory]:
    if not original_filename:
        raise InvalidInputArtifactNameError("original filename is required")

    safe_name = original_filename.replace("\\", "/").split("/")[-1].strip()
    if not safe_name or safe_name in {".", ".."}:
        raise InvalidInputArtifactNameError("original filename is invalid")

    extension = Path(safe_name).suffix.lower()
    category = _EXTENSION_CATEGORIES.get(extension)
    if category is None:
        raise UnsupportedInputArtifactTypeError(
            f"unsupported input artifact extension: {extension or '<none>'}"
        )
    return safe_name, extension, category


def inspect_input_artifact_file(
    *,
    file_stream: BinaryIO,
    original_filename: str | None,
    settings: Settings,
) -> InspectedInputArtifactFile:

    try:
        safe_name, _, category = normalize_input_artifact_filename(original_filename)
        max_size_bytes = _max_size_bytes(settings, category)
        byte_size = 0
        sha256_hash = hashlib.sha256()
        file_stream.seek(0)

        while chunk := file_stream.read(settings.upload_chunk_size_bytes):
            byte_size += len(chunk)
            if byte_size > max_size_bytes:
                raise InputArtifactTooLargeError(
                    f"input artifact exceeds the {max_size_bytes} byte limit"
                )
            sha256_hash.update(chunk)

        if byte_size == 0:
            raise EmptyInputArtifactError("input artifact is empty")

        return InspectedInputArtifactFile(
            original_filename=safe_name,
            byte_size=byte_size,
            sha256=sha256_hash.hexdigest(),
            category=category,
        )
    finally:
        file_stream.seek(0)


def _max_size_bytes(settings: Settings, category: _ArtifactCategory) -> int:
    max_size_mb = {
        "document": settings.input_artifact_document_max_size_mb,
        "table": settings.input_artifact_table_max_size_mb,
        "image": settings.input_artifact_image_max_size_mb,
    }[category]
    return max_size_mb * 1024 * 1024


def validate_declared_input_artifact_upload(
    *,
    original_filename: str | None,
    byte_size: int,
    declared_mime_type: str | None,
    client_reported_sha256: str,
    settings: Settings,
) -> DeclaredInputArtifactUpload:
    """Validate metadata without reading file bytes in the API process."""
    safe_name, _, category = normalize_input_artifact_filename(original_filename)
    if isinstance(byte_size, bool) or not isinstance(byte_size, int):
        raise ValueError("byte_size must be an integer")
    if byte_size <= 0:
        raise EmptyInputArtifactError("input artifact is empty")
    if byte_size > _max_size_bytes(settings, category):
        raise InputArtifactTooLargeError("input artifact exceeds the size limit")
    if declared_mime_type is not None:
        if not isinstance(declared_mime_type, str):
            raise ValueError("declared_mime_type must be a string or null")
        declared_mime_type = declared_mime_type.strip() or None
        if declared_mime_type is not None and len(declared_mime_type) > 255:
            raise ValueError("declared_mime_type is too long")
    if (
        not isinstance(client_reported_sha256, str)
        or len(client_reported_sha256) != 64
        or any(character not in "0123456789abcdef" for character in client_reported_sha256)
    ):
        raise ValueError(
            "client_reported_sha256 must be a 64-character lowercase hexadecimal value"
        )
    return DeclaredInputArtifactUpload(
        original_filename=safe_name,
        category=category,
        byte_size=byte_size,
        declared_mime_type=declared_mime_type,
        client_reported_sha256=client_reported_sha256,
    )


def store_input_artifact_file(
    *,
    file_stream: BinaryIO,
    original_filename: str | None,
    settings: Settings,
) -> StoredInputArtifactFile:
    """Store an untrusted file in quarantine and return verified raw metadata."""
    safe_name, extension, category = normalize_input_artifact_filename(
        original_filename
    )
    max_size_bytes = _max_size_bytes(settings, category)

    settings.input_artifact_quarantine_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid4().hex}{extension}"
    absolute_path = settings.input_artifact_quarantine_dir / stored_name
    raw_object_key = absolute_path.relative_to(settings.storage_dir).as_posix()

    byte_size = 0
    sha256_hash = hashlib.sha256()
    file_created = False
    try:
        file_stream.seek(0)
        with absolute_path.open("xb") as target_file:
            file_created = True
            while chunk := file_stream.read(settings.upload_chunk_size_bytes):
                byte_size += len(chunk)
                if byte_size > max_size_bytes:
                    raise InputArtifactTooLargeError(
                        f"input artifact exceeds the {max_size_bytes} byte limit"
                    )
                sha256_hash.update(chunk)
                target_file.write(chunk)
        if byte_size == 0:
            raise EmptyInputArtifactError("input artifact is empty")
    except Exception:
        if file_created:
            absolute_path.unlink(missing_ok=True)
        raise

    return StoredInputArtifactFile(
        original_filename=safe_name,
        raw_object_key=raw_object_key,
        absolute_path=absolute_path,
        byte_size=byte_size,
        sha256=sha256_hash.hexdigest(),
        category=category,
    )
