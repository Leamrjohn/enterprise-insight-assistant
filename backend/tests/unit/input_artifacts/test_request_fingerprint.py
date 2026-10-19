import pytest

from app.modules.input_artifacts.upload.request_fingerprint import (
    build_input_artifact_request_fingerprint,
)


_VALID_ARGUMENTS = {
    "company_id": 1,
    "submitted_by_user_id": 2,
    "conversation_id": 3,
    "kind": "attachment",
    "original_filename": "report.pdf",
    "content_sha256": "a" * 64,
}


def _build_fingerprint(**overrides: object) -> str:
    return build_input_artifact_request_fingerprint(
        **(_VALID_ARGUMENTS | overrides)
    )


def test_fingerprint_is_stable_and_changes_with_business_input() -> None:
    baseline = _build_fingerprint()

    assert baseline == _build_fingerprint()

    for overrides in (
        {"content_sha256": "b" * 64},
        {"original_filename": "revised-report.pdf"},
        {"conversation_id": 4},
        {"kind": "dataset"},
    ):
        assert _build_fingerprint(**overrides) != baseline


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("company_id", True),
        ("company_id", 0),
        ("company_id", -1),
        ("company_id", "1"),
        ("submitted_by_user_id", True),
        ("submitted_by_user_id", 0),
        ("submitted_by_user_id", -1),
        ("submitted_by_user_id", "2"),
        ("conversation_id", True),
        ("conversation_id", 0),
        ("conversation_id", -1),
        ("conversation_id", "3"),
    ],
)
def test_fingerprint_rejects_invalid_scope_identifiers(
    field_name: str,
    invalid_value: object,
) -> None:
    with pytest.raises(ValueError):
        _build_fingerprint(**{field_name: invalid_value})


def test_fingerprint_rejects_unsupported_artifact_kind() -> None:
    with pytest.raises(ValueError):
        _build_fingerprint(kind="untrusted-client-kind")


@pytest.mark.parametrize(
    "invalid_content_sha256",
    [
        "a" * 63,
        "A" * 64,
        "not-a-sha256",
        True,
    ],
)
def test_fingerprint_rejects_invalid_content_sha256(
    invalid_content_sha256: object,
) -> None:
    with pytest.raises(ValueError):
        _build_fingerprint(content_sha256=invalid_content_sha256)
