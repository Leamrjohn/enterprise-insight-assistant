from datetime import datetime

from app.modules.input_artifacts.models import (
    ArtifactProcessingJob,
    ArtifactProcessingOutboxEvent,
    InputArtifact,
    InputArtifactUploadRequest,
    InputArtifactUploadSession,
    InputArtifactVersion,
)
from sqlalchemy.orm import Session


def add_input_artifact(
    db: Session,
    *,
    company_id: int,
    uploaded_by_user_id: int,
    kind: str,
) -> InputArtifact:
    record = InputArtifact(
        company_id=company_id,
        uploaded_by_user_id=uploaded_by_user_id,
        kind=kind,
    )
    db.add(record)
    db.flush()
    return record


def add_input_artifact_version(
    db: Session,
    *,
    artifact_id: int,
    original_filename: str,
    declared_extension: str | None,
    raw_object_key: str,
    byte_size: int,
    sha256: str,
    declared_mime_type: str | None,
) -> InputArtifactVersion:
    record = InputArtifactVersion(
        artifact_id=artifact_id,
        version_number=1,
        original_filename=original_filename,
        declared_extension=declared_extension,
        raw_object_key=raw_object_key,
        byte_size=byte_size,
        sha256=sha256,
        declared_mime_type=declared_mime_type,
        status="received",
    )
    db.add(record)
    db.flush()
    return record


def get_input_artifact_version_for_company(
    db: Session,
    *,
    version_id: int,
    company_id: int,
) -> InputArtifactVersion | None:
    return (
        db.query(InputArtifactVersion)
        .join(InputArtifact, InputArtifact.id == InputArtifactVersion.artifact_id)
        .filter(
            InputArtifactVersion.id == version_id,
            InputArtifact.company_id == company_id,
        )
        .one_or_none()
    )


def get_ready_owned_input_artifact_versions(
    db: Session,
    *,
    version_ids: list[int],
    company_id: int,
    uploaded_by_user_id: int,
) -> list[InputArtifactVersion]:
    if not version_ids:
        return []
    return (
        db.query(InputArtifactVersion)
        .join(InputArtifact, InputArtifact.id == InputArtifactVersion.artifact_id)
        .filter(
            InputArtifactVersion.id.in_(version_ids),
            InputArtifactVersion.status == "ready",
            InputArtifact.company_id == company_id,
            InputArtifact.uploaded_by_user_id == uploaded_by_user_id,
        )
        .all()
    )


def get_input_artifact_upload_request(
    db: Session,
    *,
    company_id: int,
    submitted_by_user_id: int,
    conversation_id: int,
    idempotency_key: str,
) -> InputArtifactUploadRequest | None:
    return (
        db.query(InputArtifactUploadRequest)
        .filter(
            InputArtifactUploadRequest.company_id == company_id,
            InputArtifactUploadRequest.submitted_by_user_id == submitted_by_user_id,
            InputArtifactUploadRequest.conversation_id == conversation_id,
            InputArtifactUploadRequest.idempotency_key == idempotency_key,
        )
        .one_or_none()
    )


def add_receiving_input_artifact_upload_request(
    db: Session,
    *,
    company_id: int,
    submitted_by_user_id: int,
    conversation_id: int,
    idempotency_key: str,
    trace_request_id: str,
    lease_expires_at: datetime,
    request_fingerprint: str,
) -> InputArtifactUploadRequest:
    record = InputArtifactUploadRequest(
        company_id=company_id,
        submitted_by_user_id=submitted_by_user_id,
        conversation_id=conversation_id,
        idempotency_key=idempotency_key,
        status="receiving",
        trace_request_id=trace_request_id,
        lease_expires_at=lease_expires_at,
        request_fingerprint=request_fingerprint,
    )
    db.add(record)
    db.flush()
    return record


def add_input_artifact_upload_session(
    db: Session,
    *,
    public_id: str,
    company_id: int,
    submitted_by_user_id: int,
    conversation_id: int,
    idempotency_key: str,
    request_fingerprint: str,
    client_filename: str,
    client_reported_byte_size: int,
    client_reported_mime_type: str | None,
    client_reported_sha256: str,
    upload_policy_version: str,
    storage_provider: str,
    staging_object_key: str,
    upload_expires_at: datetime,
    trace_request_id: str,
) -> InputArtifactUploadSession:
    record = InputArtifactUploadSession(
        public_id=public_id,
        company_id=company_id,
        submitted_by_user_id=submitted_by_user_id,
        conversation_id=conversation_id,
        idempotency_key=idempotency_key,
        request_fingerprint=request_fingerprint,
        client_filename=client_filename,
        client_reported_byte_size=client_reported_byte_size,
        client_reported_mime_type=client_reported_mime_type,
        client_reported_sha256=client_reported_sha256,
        upload_policy_version=upload_policy_version,
        storage_provider=storage_provider,
        staging_object_key=staging_object_key,
        upload_expires_at=upload_expires_at,
        trace_request_id=trace_request_id,
    )
    db.add(record)
    db.flush()
    return record


def add_artifact_processing_job(
    db: Session,
    *,
    company_id: int,
    artifact_version_id: int,
    stage: str,
    max_attempts: int,
    trace_request_id: str,
) -> ArtifactProcessingJob:
    record = ArtifactProcessingJob(
        company_id=company_id,
        artifact_version_id=artifact_version_id,
        stage=stage,
        max_attempts=max_attempts,
        trace_request_id=trace_request_id,
    )
    db.add(record)
    db.flush()
    return record


def add_artifact_processing_outbox_event(
    db: Session,
    *,
    company_id: int,
    job_id: int,
    dispatch_generation: int,
    trace_request_id: str,
) -> ArtifactProcessingOutboxEvent:
    record = ArtifactProcessingOutboxEvent(
        company_id=company_id,
        job_id=job_id,
        dispatch_generation=dispatch_generation,
        event_type="artifact_processing_job.created",
        trace_request_id=trace_request_id,
    )
    db.add(record)
    db.flush()
    return record


def get_input_artifact_upload_session(
    db: Session,
    *,
    company_id: int,
    submitted_by_user_id: int,
    conversation_id: int,
    idempotency_key: str,
) -> InputArtifactUploadSession | None:
    return (
        db.query(InputArtifactUploadSession)
        .filter(
            InputArtifactUploadSession.company_id == company_id,
            InputArtifactUploadSession.submitted_by_user_id == submitted_by_user_id,
            InputArtifactUploadSession.conversation_id == conversation_id,
            InputArtifactUploadSession.idempotency_key == idempotency_key,
        )
        .one_or_none()
    )


def get_input_artifact_upload_session_by_public_id(
    db: Session,
    *,
    public_id: str,
    company_id: int,
    submitted_by_user_id: int,
    conversation_id: int,
    for_update: bool = False,
) -> InputArtifactUploadSession | None:
    query = db.query(InputArtifactUploadSession).filter(
        InputArtifactUploadSession.public_id == public_id,
        InputArtifactUploadSession.company_id == company_id,
        InputArtifactUploadSession.submitted_by_user_id == submitted_by_user_id,
        InputArtifactUploadSession.conversation_id == conversation_id,
    )
    if for_update:
        query = query.with_for_update()
    return query.one_or_none()
