from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from app.core.settings import get_settings
from app.modules.input_artifacts.upload.direct_upload_storage import S3DirectUploadStorage
from pydantic import SecretStr


class _FakeS3Client:
    def __init__(self) -> None:
        self.request: dict | None = None

    def generate_presigned_post(self, **kwargs: object) -> dict[str, object]:
        self.request = kwargs
        return {
            "url": "https://object-storage.example.test/input-artifacts",
            "fields": {"key": kwargs["Key"], "policy": "signed-policy"},
        }


@pytest.mark.parametrize(
    ("public_endpoint", "expected_endpoint"),
    [
        ("https://upload.example.test", "https://upload.example.test"),
        (None, "https://s3.example.test"),
    ],
)
def test_s3_direct_upload_form_binds_exact_key_size_checksum_and_public_endpoint(
    monkeypatch, public_endpoint: str | None, expected_endpoint: str
) -> None:
    fake_client = _FakeS3Client()
    client_kwargs: dict[str, object] = {}

    def client(*_args, **kwargs):
        client_kwargs.update(kwargs)
        return fake_client

    fake_boto3 = SimpleNamespace(client=client)
    monkeypatch.setitem(__import__("sys").modules, "boto3", fake_boto3)
    settings = get_settings().model_copy(
        update={
            "input_artifact_object_storage_endpoint_url": "https://s3.example.test",
            "input_artifact_object_storage_public_endpoint_url": public_endpoint,
            "input_artifact_object_storage_bucket": "quarantine-bucket",
            "input_artifact_object_storage_access_key_id": SecretStr("access-key"),
            "input_artifact_object_storage_secret_access_key": SecretStr("secret-key"),
        }
    )
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

    form = S3DirectUploadStorage(settings=settings).create_quarantine_upload_form(
        object_key="input-artifacts/quarantine/7/session/payload",
        byte_size=1024,
        sha256_hex="a" * 64,
        expires_at=expires_at,
    )

    assert form.url == "https://object-storage.example.test/input-artifacts"
    assert client_kwargs["endpoint_url"] == expected_endpoint
    assert fake_client.request is not None
    assert fake_client.request["Bucket"] == "quarantine-bucket"
    assert fake_client.request["Key"] == "input-artifacts/quarantine/7/session/payload"
    assert {"key": fake_client.request["Key"]} in fake_client.request["Conditions"]
    assert ["content-length-range", 1024, 1024] in fake_client.request["Conditions"]
    assert {
        "x-amz-checksum-algorithm": "SHA256"
    } in fake_client.request["Conditions"]
    assert "x-amz-checksum-sha256" in fake_client.request["Fields"]
