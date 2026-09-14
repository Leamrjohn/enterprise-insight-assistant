import pytest
from pydantic import ValidationError

from app.core.settings import Settings


def test_input_artifact_upload_lease_seconds_accepts_a_positive_value() -> None:
    settings = Settings(input_artifact_upload_lease_seconds=120)

    assert settings.input_artifact_upload_lease_seconds == 120


@pytest.mark.parametrize("lease_seconds", [0, -1])
def test_input_artifact_upload_lease_seconds_rejects_non_positive_values(
    lease_seconds: int,
) -> None:
    with pytest.raises(ValidationError):
        Settings(input_artifact_upload_lease_seconds=lease_seconds)
