import re
from pathlib import Path

from app.modules.input_artifacts.models import InputArtifactVersion
from app.modules.input_artifacts.repository import (
    add_input_artifact,
    add_input_artifact_version,
)
from sqlalchemy.orm import Session

_KIND_VALUES = {"attachment", "knowledge_document", "dataset"}
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _require_positive_id(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")


def _normalize_filename(original_filename: str) -> tuple[str, str | None]:
    if not isinstance(original_filename, str):
        raise ValueError("original_filename must be a string")  # noqa: TRY004 - Preserve the metadata validation contract.

    safe_name = original_filename.replace("\\", "/").split("/")[-1].strip()
    if not safe_name or safe_name in {".", ".."}:
        raise ValueError("original_filename is invalid")
    if len(safe_name) > 255:
        raise ValueError("original_filename is too long")

    extension = Path(safe_name).suffix.lower().lstrip(".") or None
    if extension is not None and len(extension) > 32:
        raise ValueError("declared extension is too long")
    return safe_name, extension


def _normalize_optional_mime_type(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("declared_mime_type must be a string or null")  # noqa: TRY004 - Preserve the metadata validation contract.
    normalized = value.strip() or None
    if normalized is not None and len(normalized) > 255:
        raise ValueError("declared_mime_type is too long")
    return normalized


def create_received_input_artifact_version(
    db: Session,
    *,
    company_id: int,
    uploaded_by_user_id: int,
    kind: str,
    original_filename: str,
    raw_object_key: str,
    byte_size: int,
    sha256: str,
    declared_mime_type: str | None = None,
    commit: bool = True,
) -> InputArtifactVersion:
    """Persist one received version.

    Set commit=False only when the caller owns the transaction and will
    commit or roll back it.
    """
    _require_positive_id(company_id, "company_id")
    _require_positive_id(uploaded_by_user_id, "uploaded_by_user_id")
    if db.info.get("tenant_company_id") != company_id:
        raise RuntimeError("database tenant scope does not match company_id")
    if kind not in _KIND_VALUES:
        raise ValueError("kind is invalid")
    if not isinstance(raw_object_key, str) or not raw_object_key.strip():
        raise ValueError("raw_object_key is required")
    if len(raw_object_key) > 512:
        raise ValueError("raw_object_key is too long")
    if isinstance(byte_size, bool) or not isinstance(byte_size, int) or byte_size < 0:
        raise ValueError("byte_size must be a non-negative integer")
    if not isinstance(sha256, str) or not _SHA256_PATTERN.fullmatch(sha256):
        raise ValueError("sha256 must be a 64-character lowercase hexadecimal value")

    safe_name, declared_extension = _normalize_filename(original_filename)
    normalized_mime_type = _normalize_optional_mime_type(declared_mime_type)

    try:
        artifact = add_input_artifact(
            db,
            company_id=company_id,
            uploaded_by_user_id=uploaded_by_user_id,
            kind=kind,
        )
        version = add_input_artifact_version(
            db,
            artifact_id=artifact.id,
            original_filename=safe_name,
            declared_extension=declared_extension,
            raw_object_key=raw_object_key,
            byte_size=byte_size,
            sha256=sha256,
            declared_mime_type=normalized_mime_type,
        )
        if commit:
            db.commit()
            db.refresh(version)
        return version
    except Exception:
        if commit:
            db.rollback()
        raise
