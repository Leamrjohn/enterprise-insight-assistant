"""Initiate direct, browser-to-object-storage attachment uploads."""

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID, uuid4

from app.core.settings import Settings
from app.modules.conversations.service import get_conversation_service
from app.modules.input_artifacts.models import InputArtifactUploadSession
from app.modules.input_artifacts.repository import (
    add_artifact_processing_job,
    add_artifact_processing_outbox_event,
    add_input_artifact_upload_session,
    get_input_artifact_upload_session,
    get_input_artifact_upload_session_by_public_id,
    get_input_artifact_version_for_company,
)
from app.modules.input_artifacts.storage import (
    DeclaredInputArtifactUpload,
    validate_declared_input_artifact_upload,
)
from app.modules.input_artifacts.upload.direct_upload_storage import (
    DirectUploadForm,
    DirectUploadObjectIntegrityError,
    DirectUploadObjectNotFoundError,
    DirectUploadStorage,
)
from app.modules.input_artifacts.upload.upload_session_fingerprint import (
    build_direct_upload_session_fingerprint,
)
from app.modules.input_artifacts.versions import create_received_input_artifact_version
from app.modules.organizations.access import CurrentCompanyContext
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

_ATTACHMENT_UPLOAD_POLICY_VERSION = "conversation-attachment-v1"
_FINALIZATION_LEASE = timedelta(minutes=2)
_SCAN_MAX_ATTEMPTS = 3


class UploadSessionFingerprintConflictError(ValueError):
    """An idempotency key was reused for a different direct upload intent."""


@dataclass(frozen=True, slots=True)
class InitiateAttachmentUploadCommand:
    context: CurrentCompanyContext
    conversation_id: int
    idempotency_key: str
    trace_request_id: str
    original_filename: str | None
    client_reported_byte_size: int
    client_reported_mime_type: str | None
    client_reported_sha256: str


@dataclass(frozen=True, slots=True)
class UploadSessionInitiationOutcome:
    session: InputArtifactUploadSession
    disposition: Literal["created", "replayed", "in_progress", "terminal"]
    upload_form: DirectUploadForm | None


@dataclass(frozen=True, slots=True)
class CompleteAttachmentUploadCommand:
    context: CurrentCompanyContext
    conversation_id: int
    upload_session_public_id: str
    trace_request_id: str


@dataclass(frozen=True, slots=True)
class UploadSessionCompletionOutcome:
    session: InputArtifactUploadSession
    disposition: Literal["completed", "replayed", "in_progress", "terminal"]
    artifact_version_id: int | None


def initiate_conversation_attachment_upload(
    db: Session,
    *,
    command: InitiateAttachmentUploadCommand,
    settings: Settings,
    direct_upload_storage: DirectUploadStorage,
) -> UploadSessionInitiationOutcome | None:
    """Create or replay a session; never receive raw bytes in this process."""
    command = _normalize_command(command)
    if db.info.get("tenant_company_id") != command.context.company.id:
        raise RuntimeError("database tenant scope does not match the current company")
    conversation = get_conversation_service(
        db,
        conversation_id=command.conversation_id,
        context=command.context,
    )
    if conversation is None:
        return None
    declared_upload = validate_declared_input_artifact_upload(
        original_filename=command.original_filename,
        byte_size=command.client_reported_byte_size,
        declared_mime_type=command.client_reported_mime_type,
        client_reported_sha256=command.client_reported_sha256,
        settings=settings,
    )
    fingerprint = build_direct_upload_session_fingerprint(
        company_id=command.context.company.id,
        submitted_by_user_id=command.context.user.id,
        conversation_id=conversation.id,
        declared_upload=declared_upload,
        upload_policy_version=_ATTACHMENT_UPLOAD_POLICY_VERSION,
    )
    return _reserve_or_replay_upload_session(
        db,
        command=command,
        declared_upload=declared_upload,
        fingerprint=fingerprint,
        settings=settings,
        direct_upload_storage=direct_upload_storage,
    )


def _reserve_or_replay_upload_session(
    db: Session,
    *,
    command: InitiateAttachmentUploadCommand,
    declared_upload: DeclaredInputArtifactUpload,
    fingerprint: str,
    settings: Settings,
    direct_upload_storage: DirectUploadStorage,
) -> UploadSessionInitiationOutcome:
    now = datetime.now(timezone.utc)
    existing = get_input_artifact_upload_session(
        db,
        company_id=command.context.company.id,
        submitted_by_user_id=command.context.user.id,
        conversation_id=command.conversation_id,
        idempotency_key=command.idempotency_key,
    )
    if existing is not None:
        return _replay_existing_session(
            db,
            session=existing,
            fingerprint=fingerprint,
            now=now,
            settings=settings,
            direct_upload_storage=direct_upload_storage,
        )

    public_id = str(uuid4())
    expires_at = now + timedelta(
        seconds=settings.input_artifact_direct_upload_ttl_seconds
    )
    object_key = (
        f"input-artifacts/quarantine/{command.context.company.id}/{public_id}/payload"
    )
    try:
        session = add_input_artifact_upload_session(
            db,
            public_id=public_id,
            company_id=command.context.company.id,
            submitted_by_user_id=command.context.user.id,
            conversation_id=command.conversation_id,
            idempotency_key=command.idempotency_key,
            request_fingerprint=fingerprint,
            client_filename=declared_upload.original_filename,
            client_reported_byte_size=declared_upload.byte_size,
            client_reported_mime_type=declared_upload.declared_mime_type,
            client_reported_sha256=declared_upload.client_reported_sha256,
            upload_policy_version=_ATTACHMENT_UPLOAD_POLICY_VERSION,
            storage_provider=direct_upload_storage.provider_name,
            staging_object_key=object_key,
            upload_expires_at=expires_at,
            trace_request_id=command.trace_request_id,
        )
        upload_form = direct_upload_storage.create_quarantine_upload_form(
            object_key=session.staging_object_key,
            byte_size=session.client_reported_byte_size,
            sha256_hex=session.client_reported_sha256,
            expires_at=session.upload_expires_at,
        )
        db.commit()
        db.refresh(session)
        return UploadSessionInitiationOutcome(session, "created", upload_form)
    except IntegrityError:
        db.rollback()
        existing = get_input_artifact_upload_session(
            db,
            company_id=command.context.company.id,
            submitted_by_user_id=command.context.user.id,
            conversation_id=command.conversation_id,
            idempotency_key=command.idempotency_key,
        )
        if existing is None:
            raise RuntimeError(
                "upload session was not visible after duplicate-key race"
            )
        return _replay_existing_session(
            db,
            session=existing,
            fingerprint=fingerprint,
            now=now,
            settings=settings,
            direct_upload_storage=direct_upload_storage,
        )
    except Exception:
        db.rollback()
        raise


def _replay_existing_session(
    db: Session,
    *,
    session: InputArtifactUploadSession,
    fingerprint: str,
    now: datetime,
    settings: Settings,
    direct_upload_storage: DirectUploadStorage,
) -> UploadSessionInitiationOutcome:
    if session.request_fingerprint != fingerprint:
        raise UploadSessionFingerprintConflictError(
            "idempotency key was reused with different upload metadata"
        )
    if session.status == "awaiting_upload":
        if session.upload_expires_at <= now:
            _expire_session(db, session=session, now=now)
            return UploadSessionInitiationOutcome(session, "terminal", None)
        upload_form = direct_upload_storage.create_quarantine_upload_form(
            object_key=session.staging_object_key,
            byte_size=session.client_reported_byte_size,
            sha256_hex=session.client_reported_sha256,
            expires_at=session.upload_expires_at,
        )
        return UploadSessionInitiationOutcome(session, "replayed", upload_form)
    if session.status == "finalizing":
        return UploadSessionInitiationOutcome(session, "in_progress", None)
    return UploadSessionInitiationOutcome(session, "terminal", None)


def _expire_session(
    db: Session,
    *,
    session: InputArtifactUploadSession,
    now: datetime,
) -> None:
    updated_count = (
        db.query(InputArtifactUploadSession)
        .filter(
            InputArtifactUploadSession.id == session.id,
            InputArtifactUploadSession.status == "awaiting_upload",
            InputArtifactUploadSession.upload_expires_at <= now,
        )
        .update(
            {
                InputArtifactUploadSession.status: "expired",
                InputArtifactUploadSession.failure_code: "upload_session_expired",
                InputArtifactUploadSession.finished_at: now,
            },
            synchronize_session=False,
        )
    )
    if updated_count != 1:
        db.rollback()
        raise RuntimeError("upload session changed while being expired")
    db.commit()
    db.refresh(session)


def complete_conversation_attachment_upload(
    db: Session,
    *,
    command: CompleteAttachmentUploadCommand,
    direct_upload_storage: DirectUploadStorage,
) -> UploadSessionCompletionOutcome | None:
    """Accept a direct upload only after object-storage metadata verification."""
    command = _normalize_completion_command(command)
    if db.info.get("tenant_company_id") != command.context.company.id:
        raise RuntimeError("database tenant scope does not match the current company")
    conversation = get_conversation_service(
        db,
        conversation_id=command.conversation_id,
        context=command.context,
    )
    if conversation is None:
        return None

    claim = _claim_upload_session_finalization(db, command=command)
    if claim.disposition != "claimed":
        return _completion_outcome_for_existing_session(
            db,
            session=claim.session,
            disposition=claim.disposition,
            company_id=command.context.company.id,
        )

    try:
        stored_object = direct_upload_storage.inspect_quarantine_object(
            object_key=claim.session.staging_object_key,
        )
    except DirectUploadObjectNotFoundError:
        return _fail_claimed_upload_session(
            db,
            command=command,
            claim=claim,
            failure_code="uploaded_object_missing",
        )
    except DirectUploadObjectIntegrityError:
        return _fail_claimed_upload_session(
            db,
            command=command,
            claim=claim,
            failure_code="uploaded_object_integrity_unavailable",
        )

    if (
        stored_object.byte_size != claim.session.client_reported_byte_size
        or stored_object.sha256_hex != claim.session.client_reported_sha256
    ):
        return _fail_claimed_upload_session(
            db,
            command=command,
            claim=claim,
            failure_code="uploaded_object_metadata_mismatch",
        )
    return _complete_claimed_upload_session(
        db,
        command=command,
        claim=claim,
        verified_byte_size=stored_object.byte_size,
        verified_sha256=stored_object.sha256_hex,
    )


@dataclass(frozen=True, slots=True)
class _FinalizationClaim:
    session: InputArtifactUploadSession
    disposition: Literal["claimed", "replayed", "in_progress", "terminal"]
    execution_id: str | None = None
    generation: int | None = None


def _claim_upload_session_finalization(
    db: Session,
    *,
    command: CompleteAttachmentUploadCommand,
) -> _FinalizationClaim:
    now = datetime.now(timezone.utc)
    session = get_input_artifact_upload_session_by_public_id(
        db,
        public_id=command.upload_session_public_id,
        company_id=command.context.company.id,
        submitted_by_user_id=command.context.user.id,
        conversation_id=command.conversation_id,
        for_update=True,
    )
    if session is None:
        return _FinalizationClaim(
            session=None,  # type: ignore[arg-type]
            disposition="terminal",
        )
    if session.status == "completed":
        db.commit()
        return _FinalizationClaim(session=session, disposition="replayed")
    if session.status in {"rejected", "expired", "failed"}:
        db.commit()
        return _FinalizationClaim(session=session, disposition="terminal")
    if session.status == "awaiting_upload" and session.upload_expires_at <= now:
        session.status = "expired"
        session.failure_code = "upload_session_expired"
        session.finished_at = now
        db.commit()
        db.refresh(session)
        return _FinalizationClaim(session=session, disposition="terminal")
    if (
        session.status == "finalizing"
        and session.finalization_lease_expires_at is not None
        and session.finalization_lease_expires_at > now
    ):
        db.commit()
        return _FinalizationClaim(session=session, disposition="in_progress")

    execution_id = str(uuid4())
    generation = session.finalization_generation + 1
    session.status = "finalizing"
    session.finalization_generation = generation
    session.finalization_execution_id = execution_id
    session.finalization_lease_expires_at = now + _FINALIZATION_LEASE
    db.commit()
    db.refresh(session)
    return _FinalizationClaim(
        session=session,
        disposition="claimed",
        execution_id=execution_id,
        generation=generation,
    )


def _completion_outcome_for_existing_session(
    db: Session,
    *,
    session: InputArtifactUploadSession | None,
    disposition: Literal["replayed", "in_progress", "terminal"],
    company_id: int,
) -> UploadSessionCompletionOutcome | None:
    if session is None:
        return None
    artifact_version_id = session.artifact_version_id
    if session.status == "completed" and artifact_version_id is not None:
        version = get_input_artifact_version_for_company(
            db,
            version_id=artifact_version_id,
            company_id=company_id,
        )
        if version is None:
            raise RuntimeError(
                "completed upload session has no readable artifact version"
            )
    return UploadSessionCompletionOutcome(
        session=session,
        disposition=disposition,
        artifact_version_id=artifact_version_id,
    )


def _fail_claimed_upload_session(
    db: Session,
    *,
    command: CompleteAttachmentUploadCommand,
    claim: _FinalizationClaim,
    failure_code: str,
) -> UploadSessionCompletionOutcome:
    session = _lock_claimed_session(db, command=command, claim=claim)
    session.status = "failed"
    session.finalization_execution_id = None
    session.finalization_lease_expires_at = None
    session.failure_code = failure_code
    session.finished_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(session)
    return UploadSessionCompletionOutcome(session, "terminal", None)


def _complete_claimed_upload_session(
    db: Session,
    *,
    command: CompleteAttachmentUploadCommand,
    claim: _FinalizationClaim,
    verified_byte_size: int,
    verified_sha256: str,
) -> UploadSessionCompletionOutcome:
    session = _lock_claimed_session(db, command=command, claim=claim)
    try:
        version = create_received_input_artifact_version(
            db,
            company_id=command.context.company.id,
            uploaded_by_user_id=command.context.user.id,
            kind="attachment",
            original_filename=session.client_filename,
            raw_object_key=session.staging_object_key,
            byte_size=verified_byte_size,
            sha256=verified_sha256,
            declared_mime_type=session.client_reported_mime_type,
            commit=False,
        )
        job = add_artifact_processing_job(
            db,
            company_id=command.context.company.id,
            artifact_version_id=version.id,
            stage="scan",
            max_attempts=_SCAN_MAX_ATTEMPTS,
            trace_request_id=command.trace_request_id,
        )
        add_artifact_processing_outbox_event(
            db,
            company_id=command.context.company.id,
            job_id=job.id,
            dispatch_generation=job.attempt_generation + 1,
            trace_request_id=command.trace_request_id,
        )
        session.status = "completed"
        session.finalization_execution_id = None
        session.finalization_lease_expires_at = None
        session.storage_verified_byte_size = verified_byte_size
        session.storage_verified_sha256 = verified_sha256
        session.artifact_version_id = version.id
        session.finished_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(session)
        return UploadSessionCompletionOutcome(session, "completed", version.id)
    except Exception:
        db.rollback()
        raise


def _lock_claimed_session(
    db: Session,
    *,
    command: CompleteAttachmentUploadCommand,
    claim: _FinalizationClaim,
) -> InputArtifactUploadSession:
    session = get_input_artifact_upload_session_by_public_id(
        db,
        public_id=command.upload_session_public_id,
        company_id=command.context.company.id,
        submitted_by_user_id=command.context.user.id,
        conversation_id=command.conversation_id,
        for_update=True,
    )
    if (
        session is None
        or session.status != "finalizing"
        or session.finalization_execution_id != claim.execution_id
        or session.finalization_generation != claim.generation
    ):
        db.rollback()
        raise RuntimeError("upload session finalization lost its lease")
    return session


def _normalize_command(
    command: InitiateAttachmentUploadCommand,
) -> InitiateAttachmentUploadCommand:
    if (
        isinstance(command.conversation_id, bool)
        or not isinstance(command.conversation_id, int)
        or command.conversation_id <= 0
    ):
        raise ValueError("conversation_id must be a positive integer")
    if (
        not isinstance(command.idempotency_key, str)
        or not command.idempotency_key.strip()
    ):
        raise ValueError("idempotency_key is required")
    idempotency_key = command.idempotency_key.strip()
    if len(idempotency_key) > 128:
        raise ValueError("idempotency_key is too long")
    if (
        not isinstance(command.trace_request_id, str)
        or not command.trace_request_id.strip()
    ):
        raise ValueError("trace_request_id is required")
    trace_request_id = command.trace_request_id.strip()
    if len(trace_request_id) > 128:
        raise ValueError("trace_request_id is too long")
    return replace(
        command,
        idempotency_key=idempotency_key,
        trace_request_id=trace_request_id,
    )


def _normalize_completion_command(
    command: CompleteAttachmentUploadCommand,
) -> CompleteAttachmentUploadCommand:
    if (
        isinstance(command.conversation_id, bool)
        or not isinstance(command.conversation_id, int)
        or command.conversation_id <= 0
    ):
        raise ValueError("conversation_id must be a positive integer")
    try:
        upload_session_public_id = str(UUID(command.upload_session_public_id))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("upload_session_public_id must be a UUID") from exc
    if (
        not isinstance(command.trace_request_id, str)
        or not command.trace_request_id.strip()
    ):
        raise ValueError("trace_request_id is required")
    trace_request_id = command.trace_request_id.strip()
    if len(trace_request_id) > 128:
        raise ValueError("trace_request_id is too long")
    return replace(
        command,
        upload_session_public_id=upload_session_public_id,
        trace_request_id=trace_request_id,
    )
