from pathlib import Path
from types import SimpleNamespace

from pydantic import SecretStr

from app.core.settings import get_settings
from app.modules.input_artifacts.processing_storage import S3ArtifactProcessingStorage


class _FakeS3Client:
    def __init__(self) -> None:
        self.download_request: tuple[str, str, str] | None = None
        self.put_request: dict[str, object] | None = None

    def download_file(self, bucket: str, key: str, destination: str) -> None:
        self.download_request = (bucket, key, destination)
        Path(destination).write_bytes(b"raw artifact")

    def put_object(self, **kwargs: object) -> None:
        self.put_request = kwargs


def _storage(monkeypatch) -> tuple[S3ArtifactProcessingStorage, _FakeS3Client]:
    client = _FakeS3Client()
    monkeypatch.setitem(
        __import__("sys").modules,
        "boto3",
        SimpleNamespace(client=lambda *_args, **_kwargs: client),
    )
    settings = get_settings().model_copy(
        update={
            "input_artifact_object_storage_endpoint_url": "https://s3.example.test",
            "input_artifact_object_storage_bucket": "artifact-bucket",
            "input_artifact_object_storage_access_key_id": SecretStr("access-key"),
            "input_artifact_object_storage_secret_access_key": SecretStr("secret-key"),
        }
    )
    return S3ArtifactProcessingStorage(settings=settings), client


def test_downloaded_quarantine_object_is_hashed_before_processing(
    monkeypatch,
    tmp_path: Path,
) -> None:
    storage, client = _storage(monkeypatch)
    destination = tmp_path / "raw" / "payload"

    result = storage.download_quarantine_object(
        object_key="input-artifacts/quarantine/7/session/payload",
        destination_path=destination,
    )

    assert client.download_request == (
        "artifact-bucket",
        "input-artifacts/quarantine/7/session/payload",
        str(destination),
    )
    assert result.object_key == "input-artifacts/quarantine/7/session/payload"
    assert result.byte_size == len(b"raw artifact")
    assert result.sha256_hex == "d376512f3901b0a8347d0221155af8c527795b23b9b884d8d25484149ea0da47"


def test_parsed_object_write_binds_its_checksum_and_prefix(monkeypatch) -> None:
    storage, client = _storage(monkeypatch)

    result = storage.write_parsed_object(
        object_key="input-artifacts/parsed/7/1/manifest.json",
        content=b'{"kind":"manifest"}',
        content_type="application/json",
    )

    assert client.put_request is not None
    assert client.put_request["Bucket"] == "artifact-bucket"
    assert client.put_request["Key"] == result.object_key
    assert client.put_request["ChecksumAlgorithm"] == "SHA256"
    assert result.byte_size == len(b'{"kind":"manifest"}')
    assert result.sha256_hex == "2d511d9adee14cb3f84921d93b664c157d08950fe7f3028e4beb7557f6a9c019"
