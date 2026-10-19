"""Reservation of an upload request before its untrusted bytes are stored."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.organizations.access import CurrentCompanyContext
from app.modules.input_artifacts.models import InputArtifactUploadRequest
from app.modules.input_artifacts.repository import (
    add_receiving_input_artifact_upload_request,
    get_input_artifact_upload_request,
    get_input_artifact_version_for_company,
)
from app.modules.conversations.service import get_conversation_service


@dataclass(frozen=True)
class UploadRequestReservation:
    request: InputArtifactUploadRequest
    disposition: Literal["reserved", "in_progress", "terminal"]


class UploadRequestFencedError(RuntimeError):
    """The request no longer owns the valid upload lease."""


class UploadRequestFingerprintConflictError(ValueError):
    """The idempotency key was reused with different request content."""





def reserve_input_artifact_upload_request(
    db: Session,
    *,
    context: CurrentCompanyContext,
    conversation_id: int,
    idempotency_key: str,
    trace_request_id: str,
    lease_duration: timedelta,
    request_fingerprint: str,
) -> UploadRequestReservation | None:
    """Reserve one attachment upload without allowing a stale request to win."""
    if (
        isinstance(conversation_id, bool)
        or not isinstance(conversation_id, int)
        or conversation_id <= 0
    ):
        raise ValueError("conversation_id must be a positive integer")
    if not isinstance(idempotency_key, str) or not (
        idempotency_key := idempotency_key.strip()
    ):
        raise ValueError("idempotency_key is required")
    if len(idempotency_key) > 128:
        raise ValueError("idempotency_key is too long")
    if (
        not isinstance(request_fingerprint, str)
        or len(request_fingerprint) != 64
        or any(character not in "0123456789abcdef" for character in request_fingerprint)
    ):
        raise ValueError(
            "request_fingerprint must be a 64-character lowercase hexadecimal value"
        )
    if not isinstance(trace_request_id, str) or not (
        trace_request_id := trace_request_id.strip()
    ):
        raise ValueError("trace_request_id is required")
    if len(trace_request_id) > 128:
        raise ValueError("trace_request_id is too long")
    if not isinstance(lease_duration, timedelta) or lease_duration <= timedelta():
        raise ValueError("lease_duration must be positive")
    if db.info.get("tenant_company_id") != context.company.id:
        raise RuntimeError("database tenant scope does not match the current company")

    conversation = get_conversation_service(
        db,
        conversation_id=conversation_id,
        context=context,
    )
    if conversation is None:
        return None

    now = datetime.now(timezone.utc)
    lease_expires_at = now + lease_duration
    existing = get_input_artifact_upload_request(
        db,
        company_id=context.company.id,
        submitted_by_user_id=context.user.id,
        conversation_id=conversation.id,
        idempotency_key=idempotency_key,
    )

    if existing is None:
        try:
            record = add_receiving_input_artifact_upload_request(
                db,
                company_id=context.company.id,
                submitted_by_user_id=context.user.id,
                conversation_id=conversation.id,
                idempotency_key=idempotency_key,
                trace_request_id=trace_request_id,
                lease_expires_at=lease_expires_at,
                request_fingerprint=request_fingerprint,
            )
            db.commit()
            db.refresh(record)
            return UploadRequestReservation(record, "reserved")
        except IntegrityError:
            db.rollback()
            existing = get_input_artifact_upload_request(
                db,
                company_id=context.company.id,
                submitted_by_user_id=context.user.id,
                conversation_id=conversation.id,
                idempotency_key=idempotency_key,
            )
            if existing is None:
                raise RuntimeError(
                    "upload request was not visible after a duplicate-key race"
                )
        except Exception:
            db.rollback()
            raise
    if existing.request_fingerprint != request_fingerprint:
        raise UploadRequestFingerprintConflictError(
            "idempotency key was reused with different request content"
        )
    if existing.status in {"completed", "rejected", "failed"}:
        return UploadRequestReservation(existing, "terminal")
    if existing.status != "receiving" or existing.lease_expires_at is None:
        raise RuntimeError("upload request has an invalid persisted state")
    if existing.lease_expires_at > now:
        return UploadRequestReservation(existing, "in_progress")

    try:
        updated_count = (
            db.query(InputArtifactUploadRequest)
            .filter(
                InputArtifactUploadRequest.id == existing.id,
                InputArtifactUploadRequest.status == "receiving",
                InputArtifactUploadRequest.attempt_generation
                == existing.attempt_generation,
                InputArtifactUploadRequest.lease_expires_at <= now,
            )
            .update(
                {
                    InputArtifactUploadRequest.attempt_generation: InputArtifactUploadRequest.attempt_generation
                    + 1,
                    InputArtifactUploadRequest.trace_request_id: trace_request_id,
                    InputArtifactUploadRequest.lease_expires_at: lease_expires_at,
                },
                synchronize_session=False,
            )
        )
        if updated_count == 1:
            db.commit()
            db.expire_all()
            record = get_input_artifact_upload_request(
                db,
                company_id=context.company.id,
                submitted_by_user_id=context.user.id,
                conversation_id=conversation.id,
                idempotency_key=idempotency_key,
            )
            if record is None:
                raise RuntimeError("reserved upload request disappeared")
            return UploadRequestReservation(record, "reserved")
        db.rollback()
    except Exception:
        db.rollback()
        raise

    current = get_input_artifact_upload_request(
        db,
        company_id=context.company.id,
        submitted_by_user_id=context.user.id,
        conversation_id=conversation.id,
        idempotency_key=idempotency_key,
    )
    if current is None:
        raise RuntimeError("upload request disappeared during lease recovery")
    if current.status == "receiving":
        return UploadRequestReservation(current, "in_progress")
    return UploadRequestReservation(current, "terminal")


def complete_input_artifact_upload_request(
    db: Session,
    *,
    context: CurrentCompanyContext,
    conversation_id: int,
    idempotency_key: str,
    attempt_generation: int,
    payload_hash: str,
    artifact_version_id: int,
) -> InputArtifactUploadRequest | None:
    """Publish a stored version only while this request still owns its lease.

    The caller may create the version with ``commit=False`` before calling
    this function. A fencing failure rolls that pending version back too.
    """
    if (
        isinstance(conversation_id, bool)
        or not isinstance(conversation_id, int)
        or conversation_id <= 0
    ):
        raise ValueError("conversation_id must be a positive integer")
    if not isinstance(idempotency_key, str) or not (
        idempotency_key := idempotency_key.strip()
    ):
        raise ValueError("idempotency_key is required")
    if len(idempotency_key) > 128:
        raise ValueError("idempotency_key is too long")
    if (
        isinstance(attempt_generation, bool)
        or not isinstance(attempt_generation, int)
        or attempt_generation <= 0
    ):
        raise ValueError("attempt_generation must be a positive integer")
    if (
        not isinstance(payload_hash, str)
        or len(payload_hash) != 64
        or any(character not in "0123456789abcdef" for character in payload_hash)
    ):
        raise ValueError(
            "payload_hash must be a 64-character lowercase hexadecimal value"
        )
    if (
        isinstance(artifact_version_id, bool)
        or not isinstance(artifact_version_id, int)
        or artifact_version_id <= 0
    ):
        raise ValueError("artifact_version_id must be a positive integer")
    if db.info.get("tenant_company_id") != context.company.id:
        raise RuntimeError("database tenant scope does not match the current company")

    conversation = get_conversation_service(
        db,
        conversation_id=conversation_id,
        context=context,
    )
    if conversation is None:
        return None

    try:
        version = get_input_artifact_version_for_company(
            db,
            version_id=artifact_version_id,
            company_id=context.company.id,
        )
        if version is None:
            raise PermissionError(
                "artifact version is not available in the current company"
            )

        now = datetime.now(timezone.utc)
        updated_count = (
            db.query(InputArtifactUploadRequest)
            .filter(
                InputArtifactUploadRequest.company_id == context.company.id,
                InputArtifactUploadRequest.submitted_by_user_id == context.user.id,
                InputArtifactUploadRequest.conversation_id == conversation.id,
                InputArtifactUploadRequest.idempotency_key == idempotency_key,
                InputArtifactUploadRequest.status == "receiving",
                InputArtifactUploadRequest.attempt_generation == attempt_generation,
                InputArtifactUploadRequest.lease_expires_at > now,
            )
            .update(
                {
                    InputArtifactUploadRequest.status: "completed",
                    InputArtifactUploadRequest.payload_hash: payload_hash,
                    InputArtifactUploadRequest.artifact_version_id: version.id,
                    InputArtifactUploadRequest.lease_expires_at: None,
                    InputArtifactUploadRequest.finished_at: now,
                },
                synchronize_session=False,
            )
        )
        if updated_count != 1:
            raise UploadRequestFencedError(
                "upload request no longer owns the active lease"
            )
        db.commit()
        db.expire_all()
        record = get_input_artifact_upload_request(
            db,
            company_id=context.company.id,
            submitted_by_user_id=context.user.id,
            conversation_id=conversation.id,
            idempotency_key=idempotency_key,
        )
        if record is None:
            raise RuntimeError("completed upload request disappeared")
        return record
    except Exception:
        db.rollback()
        raise


def finish_upload_request_with_error(
    db: Session,
    *,
    context: CurrentCompanyContext,
    conversation_id: int,
    idempotency_key: str,
    attempt_generation: int,
    status: Literal["rejected", "failed"],
    error_code: str,
) -> InputArtifactUploadRequest | None:
    if (
        isinstance(conversation_id, bool)
        or not isinstance(conversation_id, int)
        or conversation_id <= 0
    ):
        raise ValueError("conversation_id must be a positive integer")
    if not isinstance(idempotency_key, str) or not (
        idempotency_key := idempotency_key.strip()
    ):
        raise ValueError("idempotency_key is required")
    if len(idempotency_key) > 128:
        raise ValueError("idempotency_key is too long")
    if (
        isinstance(attempt_generation, bool)
        or not isinstance(attempt_generation, int)
        or attempt_generation <= 0
    ):
        raise ValueError("attempt_generation must be a positive integer")
    if status not in {"rejected", "failed"}:
        raise ValueError("status must be rejected or failed")
    if not isinstance(error_code, str) or not (error_code := error_code.strip()):
        raise ValueError("error_code is required")
    if len(error_code) > 64:
        raise ValueError("error_code is too long")
    if db.info.get("tenant_company_id") != context.company.id:
        raise RuntimeError("database tenant scope does not match the current company")
    conversation = get_conversation_service(
        db,
        conversation_id=conversation_id,
        context=context,
    )
    if conversation is None:
        return None
    try:
        now = datetime.now(timezone.utc)
        updated_count = (
            db.query(InputArtifactUploadRequest)
            .filter(
                InputArtifactUploadRequest.company_id == context.company.id,
                InputArtifactUploadRequest.submitted_by_user_id == context.user.id,
                InputArtifactUploadRequest.conversation_id == conversation.id,
                InputArtifactUploadRequest.idempotency_key == idempotency_key,
                InputArtifactUploadRequest.status == "receiving",
                InputArtifactUploadRequest.attempt_generation == attempt_generation,
                InputArtifactUploadRequest.lease_expires_at > now,
            )
            .update(
                {
                    InputArtifactUploadRequest.status: status,
                    InputArtifactUploadRequest.error_code: error_code,
                    InputArtifactUploadRequest.lease_expires_at: None,
                    InputArtifactUploadRequest.finished_at: now,
                },
                synchronize_session=False,
            )
        )
        if updated_count != 1:
            raise UploadRequestFencedError(
                "upload request no longer owns the active lease"
            )
        db.commit()
        db.expire_all()
        record = get_input_artifact_upload_request(
            db,
            company_id=context.company.id,
            submitted_by_user_id=context.user.id,
            conversation_id=conversation.id,
            idempotency_key=idempotency_key,
        )
        if record is None:
            raise RuntimeError("finished upload request disappeared")
        return record
    except Exception:
        db.rollback()
        raise
