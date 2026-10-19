"""S3-compatible direct upload contract for quarantined input artifacts."""

import base64
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.core.settings import Settings


class DirectUploadStorageUnavailableError(RuntimeError):
    """No correctly configured provider can issue a direct upload policy."""


class DirectUploadObjectNotFoundError(RuntimeError):
    """The browser reported completion before its quarantined object exists."""


class DirectUploadObjectIntegrityError(RuntimeError):
    """The provider cannot return the integrity metadata required for acceptance."""


@dataclass(frozen=True, slots=True)
class DirectUploadForm:
    url: str
    fields: dict[str, str]
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class StoredQuarantineObject:
    byte_size: int
    sha256_hex: str


class DirectUploadStorage(Protocol):
    provider_name: str

    def create_quarantine_upload_form(
        self,
        *,
        object_key: str,
        byte_size: int,
        sha256_hex: str,
        expires_at: datetime,
    ) -> DirectUploadForm: ...

    def inspect_quarantine_object(
        self,
        *,
        object_key: str,
    ) -> StoredQuarantineObject: ...


class S3DirectUploadStorage:
    provider_name = "s3-compatible"

    def __init__(self, *, settings: Settings) -> None:
        if not _has_complete_s3_configuration(settings):
            raise DirectUploadStorageUnavailableError(
                "direct object storage is not configured"
            )
        self._settings = settings

    def create_quarantine_upload_form(
        self,
        *,
        object_key: str,
        byte_size: int,
        sha256_hex: str,
        expires_at: datetime,
    ) -> DirectUploadForm:
        try:
            import boto3
        except ImportError as exc:
            raise DirectUploadStorageUnavailableError(
                "boto3 is required for direct object storage uploads"
            ) from exc

        remaining_seconds = int((expires_at - datetime.now(expires_at.tzinfo)).total_seconds())
        if remaining_seconds <= 0:
            raise ValueError("direct upload form expiry must be in the future")
        checksum_base64 = base64.b64encode(bytes.fromhex(sha256_hex)).decode("ascii")
        client = boto3.client(
            "s3",
            endpoint_url=(
                self._settings.input_artifact_object_storage_public_endpoint_url
                or self._settings.input_artifact_object_storage_endpoint_url
            ),
            region_name=self._settings.input_artifact_object_storage_region,
            aws_access_key_id=self._settings.input_artifact_object_storage_access_key_id.get_secret_value(),
            aws_secret_access_key=self._settings.input_artifact_object_storage_secret_access_key.get_secret_value(),
        )
        fields = {
            "key": object_key,
            "x-amz-checksum-algorithm": "SHA256",
            "x-amz-checksum-sha256": checksum_base64,
            "success_action_status": "201",
        }
        policy = client.generate_presigned_post(
            Bucket=self._settings.input_artifact_object_storage_bucket,
            Key=object_key,
            Fields=fields,
            Conditions=[
                {"key": object_key},
                {"x-amz-checksum-algorithm": "SHA256"},
                {"x-amz-checksum-sha256": checksum_base64},
                {"success_action_status": "201"},
                ["content-length-range", byte_size, byte_size],
            ],
            ExpiresIn=remaining_seconds,
        )
        return DirectUploadForm(
            url=policy["url"],
            fields={key: str(value) for key, value in policy["fields"].items()},
            expires_at=expires_at,
        )

    def inspect_quarantine_object(
        self,
        *,
        object_key: str,
    ) -> StoredQuarantineObject:
        try:
            import boto3
        except ImportError as exc:
            raise DirectUploadStorageUnavailableError(
                "boto3 is required for direct object storage uploads"
            ) from exc

        client = boto3.client(
            "s3",
            endpoint_url=self._settings.input_artifact_object_storage_endpoint_url,
            region_name=self._settings.input_artifact_object_storage_region,
            aws_access_key_id=self._settings.input_artifact_object_storage_access_key_id.get_secret_value(),
            aws_secret_access_key=self._settings.input_artifact_object_storage_secret_access_key.get_secret_value(),
        )
        try:
            response = client.head_object(
                Bucket=self._settings.input_artifact_object_storage_bucket,
                Key=object_key,
                ChecksumMode="ENABLED",
            )
        except Exception as exc:
            error_code = str(
                getattr(exc, "response", {}).get("Error", {}).get("Code", "")
            )
            if error_code in {"404", "NoSuchKey", "NotFound"}:
                raise DirectUploadObjectNotFoundError(
                    "quarantined object was not found"
                ) from exc
            raise DirectUploadStorageUnavailableError(
                "direct object storage could not inspect the quarantined object"
            ) from exc

        checksum_base64 = response.get("ChecksumSHA256")
        if not isinstance(checksum_base64, str):
            raise DirectUploadObjectIntegrityError(
                "object storage did not return SHA-256 checksum metadata"
            )
        try:
            sha256_hex = base64.b64decode(checksum_base64, validate=True).hex()
        except ValueError as exc:
            raise DirectUploadObjectIntegrityError(
                "object storage returned an invalid SHA-256 checksum"
            ) from exc
        byte_size = response.get("ContentLength")
        if isinstance(byte_size, bool) or not isinstance(byte_size, int) or byte_size < 0:
            raise DirectUploadObjectIntegrityError(
                "object storage returned an invalid object length"
            )
        return StoredQuarantineObject(byte_size=byte_size, sha256_hex=sha256_hex)


def get_direct_upload_storage(settings: Settings) -> DirectUploadStorage:
    return S3DirectUploadStorage(settings=settings)


def _has_complete_s3_configuration(settings: Settings) -> bool:
    return all(
        (
            settings.input_artifact_object_storage_endpoint_url,
            settings.input_artifact_object_storage_bucket,
            (
                settings.input_artifact_object_storage_access_key_id.get_secret_value()
                if settings.input_artifact_object_storage_access_key_id is not None
                else None
            ),
            (
                settings.input_artifact_object_storage_secret_access_key.get_secret_value()
                if settings.input_artifact_object_storage_secret_access_key is not None
                else None
            ),
        )
    )
