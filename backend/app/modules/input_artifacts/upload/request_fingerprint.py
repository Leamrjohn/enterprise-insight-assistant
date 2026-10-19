import hashlib
import json
from app.modules.input_artifacts.storage import (
    normalize_input_artifact_filename,
)


_INPUT_ARTIFACT_KINDS = frozenset(
    {"attachment", "dataset", "knowledge_document"}
)
_LOWERCASE_HEXADECIMAL_CHARACTERS = frozenset("0123456789abcdef")


def _validate_positive_identifier(value: object, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def _validate_input_artifact_kind(kind: object) -> str:
    if not isinstance(kind, str) or kind not in _INPUT_ARTIFACT_KINDS:
        raise ValueError("kind must be a supported input artifact kind")
    return kind


def _validate_content_sha256(content_sha256: object) -> str:
    if (
        not isinstance(content_sha256, str)
        or len(content_sha256) != 64
        or any(
            character not in _LOWERCASE_HEXADECIMAL_CHARACTERS
            for character in content_sha256
        )
    ):
        raise ValueError(
            "content_sha256 must be a 64-character lowercase hexadecimal value"
        )
    return content_sha256


def build_input_artifact_request_fingerprint(
    *,
    company_id: int,
    submitted_by_user_id: int,
    conversation_id: int,
    kind: str,
    original_filename: str | None,
    content_sha256: str,
) -> str:
    company_id = _validate_positive_identifier(
        company_id,
        field_name="company_id",
    )
    submitted_by_user_id = _validate_positive_identifier(
        submitted_by_user_id,
        field_name="submitted_by_user_id",
    )
    conversation_id = _validate_positive_identifier(
        conversation_id,
        field_name="conversation_id",
    )
    kind = _validate_input_artifact_kind(kind)
    content_sha256 = _validate_content_sha256(content_sha256)
    safe_filename, _, _ = normalize_input_artifact_filename(original_filename)
    payload = {
        "fingerprint_version": 1,
        "company_id": company_id,
        "submitted_by_user_id": submitted_by_user_id,
        "conversation_id": conversation_id,
        "kind": kind,
        "original_filename": safe_filename,
        "content_sha256": content_sha256,
    }
    canonical_payload = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")

    return hashlib.sha256(canonical_payload).hexdigest()
