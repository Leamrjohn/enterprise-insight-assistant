"""Controlled object-storage access used only by artifact-processing Workers."""

import base64
from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Protocol

from app.core.settings import Settings


_QUARANTINE_PREFIX = "input-artifacts/quarantine/"
_PARSED_PREFIX = "input-artifacts/parsed/"


class ArtifactProcessingStorageUnavailableError(RuntimeError):
    """The configured object storage cannot serve the processing Worker."""


class ArtifactProcessingObjectNotFoundError(RuntimeError):
    """A quarantined object expected by a persisted Version is unavailable."""


@dataclass(frozen=True, slots=True)
class StoredProcessingObject:
    object_key: str
    byte_size: int
    sha256_hex: str


class ArtifactProcessingStorage(Protocol):
    provider_name: str

    def download_quarantine_object(
        self,
        *,
        object_key: str,
        destination_path: Path,
    ) -> StoredProcessingObject: ...

    def write_parsed_object(
        self,
        *,
        object_key: str,
        content: bytes,
        content_type: str,
    ) -> StoredProcessingObject: ...


class S3ArtifactProcessingStorage:
    provider_name = "s3-compatible"

    def __init__(self, *, settings: Settings) -> None:
        if not _has_complete_s3_configuration(settings):
            raise ArtifactProcessingStorageUnavailableError(
                "artifact processing object storage is not configured"
            )
        self._settings = settings

    def download_quarantine_object(
        self,
        *,
        object_key: str,
        destination_path: Path,
    ) -> StoredProcessingObject:
        _require_object_key(object_key, prefix=_QUARANTINE_PREFIX)
        if destination_path.exists():
            raise ValueError("processing download destination already exists")
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._client().download_file(
                self._settings.input_artifact_object_storage_bucket,
                object_key,
                str(destination_path),
            )
        except Exception as exc:
            destination_path.unlink(missing_ok=True)
            if _is_not_found_error(exc):
                raise ArtifactProcessingObjectNotFoundError(
                    "quarantined object was not found"
                ) from exc
            raise ArtifactProcessingStorageUnavailableError(
                "object storage could not download the quarantined object"
            ) from exc
        byte_size, sha256_hex = _file_size_and_sha256(destination_path)
        return StoredProcessingObject(object_key, byte_size, sha256_hex)

    def write_parsed_object(
        self,
        *,
        object_key: str,
        content: bytes,
        content_type: str,
    ) -> StoredProcessingObject:
        _require_object_key(object_key, prefix=_PARSED_PREFIX)
        if not isinstance(content, bytes):
            raise TypeError("parsed object content must be bytes")
        if not isinstance(content_type, str) or not content_type.strip():
            raise ValueError("parsed object content_type is invalid")
        sha256_hex = hashlib.sha256(content).hexdigest()
        try:
            self._client().put_object(
                Bucket=self._settings.input_artifact_object_storage_bucket,
                Key=object_key,
                Body=content,
                ContentType=content_type.strip(),
                ChecksumAlgorithm="SHA256",
                ChecksumSHA256=base64.b64encode(bytes.fromhex(sha256_hex)).decode(
                    "ascii"
                ),
            )
        except Exception as exc:
            raise ArtifactProcessingStorageUnavailableError(
                "object storage could not write the parsed object"
            ) from exc
        return StoredProcessingObject(object_key, len(content), sha256_hex)

    def _client(self):
        try:
            import boto3
        except ImportError as exc:
            raise ArtifactProcessingStorageUnavailableError(
                "boto3 is required for artifact processing object storage"
            ) from exc
        return boto3.client(
            "s3",
            endpoint_url=self._settings.input_artifact_object_storage_endpoint_url,
            region_name=self._settings.input_artifact_object_storage_region,
            aws_access_key_id=(
                self._settings.input_artifact_object_storage_access_key_id.get_secret_value()
            ),
            aws_secret_access_key=(
                self._settings.input_artifact_object_storage_secret_access_key.get_secret_value()
            ),
        )


def get_artifact_processing_storage(settings: Settings) -> ArtifactProcessingStorage:
    return S3ArtifactProcessingStorage(settings=settings)


def _require_object_key(object_key: str, *, prefix: str) -> None:
    if not isinstance(object_key, str) or not object_key.startswith(prefix):
        raise ValueError(f"object key must be inside {prefix}")
    if len(object_key) > 512 or ".." in object_key or "\\" in object_key:
        raise ValueError("object key is invalid")


def _file_size_and_sha256(path: Path) -> tuple[int, str]:
    sha256 = hashlib.sha256()
    byte_size = 0
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            byte_size += len(chunk)
            sha256.update(chunk)
    return byte_size, sha256.hexdigest()


def _is_not_found_error(exc: Exception) -> bool:
    error_code = str(getattr(exc, "response", {}).get("Error", {}).get("Code", ""))
    return error_code in {"404", "NoSuchKey", "NotFound"}


def _has_complete_s3_configuration(settings: Settings) -> bool:
    return all(
        (
            settings.input_artifact_object_storage_endpoint_url,
            settings.input_artifact_object_storage_bucket,
            settings.input_artifact_object_storage_access_key_id.get_secret_value()
            if settings.input_artifact_object_storage_access_key_id is not None
            else None,
            settings.input_artifact_object_storage_secret_access_key.get_secret_value()
            if settings.input_artifact_object_storage_secret_access_key is not None
            else None,
        )
    )
