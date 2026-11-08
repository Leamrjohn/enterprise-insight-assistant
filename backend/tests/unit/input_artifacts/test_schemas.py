import pytest
from app.modules.input_artifacts.schemas import (
    InputArtifactUploadOut,
    InputArtifactVersionReceiptOut,
)
from pydantic import ValidationError


def test_upload_response_exposes_only_the_public_receipt_fields() -> None:
    response = InputArtifactUploadOut(
        upload_request_id=1,
        upload_status="completed",
        attempt_generation=1,
        artifact_version=InputArtifactVersionReceiptOut(
            version_id=2,
            status="received",
        ),
    )

    assert response.model_dump() == {
        "upload_request_id": 1,
        "upload_status": "completed",
        "attempt_generation": 1,
        "artifact_version": {
            "version_id": 2,
            "status": "received",
        },
        "error_code": None,
    }


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("upload_request_id", 0),
        ("attempt_generation", 0),
        ("upload_status", "ready"),
    ],
)
def test_upload_response_rejects_invalid_public_state(
    field_name: str,
    invalid_value: object,
) -> None:
    payload = {
        "upload_request_id": 1,
        "upload_status": "receiving",
        "attempt_generation": 1,
    }
    payload[field_name] = invalid_value

    with pytest.raises(ValidationError):
        InputArtifactUploadOut(**payload)


def test_artifact_version_receipt_rejects_invalid_version_state() -> None:
    with pytest.raises(ValidationError):
        InputArtifactVersionReceiptOut(version_id=0, status="unknown")
