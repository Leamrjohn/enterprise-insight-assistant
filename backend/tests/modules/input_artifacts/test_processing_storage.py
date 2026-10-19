from pathlib import Path
from types import SimpleNamespace

from pydantic import SecretStr

from app.core.settings import get_settings
from app.modules.input_artifacts.processing_storage import S3ArtifactProcessingStorage


class _FakeS3Client:
    def __init__(self) -> None:
        self.download_request: tuple[str, str, str] | None = None
        self.put_request: dict[str, object] | None = None
        self.put_body: bytes | None = None

    def download_file(self, bucket: str, key: str, destination: str) -> None:
        self.download_request = (bucket, key, destination)
        Path(destination).write_bytes(b"raw artifact")

    def put_object(self, **kwargs: object) -> None:
        self.put_request = kwargs
        body = kwargs["Body"]
        self.put_body = body.read() if hasattr(body, "read") else body


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


def test_downloaded_parsed_object_uses_the_parsed_prefix(monkeypatch, tmp_path: Path) -> None:
    storage, client = _storage(monkeypatch)
    destination = tmp_path / "parsed" / "manifest.json"

    storage.download_parsed_object(
        object_key="input-artifacts/parsed/7/1/manifest.json",
        destination_path=destination,
    )

    assert client.download_request == (
        "artifact-bucket",
        "input-artifacts/parsed/7/1/manifest.json",
        str(destination),
    )


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


def test_parsed_file_write_streams_a_local_file_with_its_checksum(monkeypatch, tmp_path: Path) -> None:
    storage, client = _storage(monkeypatch)
    source = tmp_path / "extracted.txt"
    source.write_bytes(b"parsed text")

    result = storage.write_parsed_file(
        object_key="input-artifacts/parsed/7/1/extracted.txt",
        source_path=source,
        content_type="text/plain; charset=utf-8",
    )

    assert client.put_request is not None
    assert client.put_body == b"parsed text"
    assert client.put_request["ContentLength"] == len(b"parsed text")
    assert result.sha256_hex == "2ca0fd2a7fe934dcd54ba71b55f7c22bba75a11ced3f655bcc683e7c24743ad8"
