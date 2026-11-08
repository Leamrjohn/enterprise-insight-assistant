from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

UploadRequestStatus = Literal[
    "receiving",
    "completed",
    "rejected",
    "failed",
]

InputArtifactVersionStatus = Literal[
    "received",
    "scanning",
    "parsing",
    "ready",
    "rejected",
    "failed",
]


class InputArtifactVersionReceiptOut(BaseModel):
    version_id: int = Field(gt=0)
    status: InputArtifactVersionStatus


class InputArtifactUploadOut(BaseModel):
    upload_request_id: int = Field(gt=0)
    upload_status: UploadRequestStatus
    attempt_generation: int = Field(ge=1)
    artifact_version: InputArtifactVersionReceiptOut | None = None
    error_code: str | None = None


UploadSessionStatus = Literal[
    "awaiting_upload",
    "finalizing",
    "completed",
    "rejected",
    "expired",
    "failed",
]


class AttachmentUploadSessionInitiate(BaseModel):
    """Fields are populated by the client from the selected File object."""

    filename: str = Field(min_length=1, max_length=255)
    byte_size: int = Field(gt=0)
    mime_type: str | None = Field(default=None, max_length=255)
    sha256: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")


class DirectUploadFormOut(BaseModel):
    method: Literal["POST"] = "POST"
    url: str
    fields: dict[str, str]
    expires_at: datetime


class AttachmentUploadSessionOut(BaseModel):
    upload_session_id: str = Field(min_length=36, max_length=36)
    upload_status: UploadSessionStatus
    upload: DirectUploadFormOut | None = None
    artifact_version: InputArtifactVersionReceiptOut | None = None
    error_code: str | None = None
