import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.modules.input_artifacts.models import (
    ArtifactParseResult,
    ArtifactProcessingAttempt,
    ArtifactProcessingJob,
    ArtifactProcessingOutboxEvent,
    InputArtifactVersion,
)
from sqlalchemy import select, update
from sqlalchemy.orm import Session

_SHA256_HEX_PATTERN = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class ClaimedProcessingJob:
    company_id: int
    job_id: int
    artifact_version_id: int
    execution_id: str
    generation: int
    trace_request_id: str


@dataclass(frozen=True, slots=True)
class ExpiredScanJobRecovery:
    outcome: str  # "requeued" | "failed"
    dispatch_generation: int | None


@dataclass(frozen=True, slots=True)
class ScanJobFailureOutcome:
    outcome: str  # "requeued" | "failed"
    dispatch_generation: int | None


def claim_scan_job_for_processing(
    db: Session,
    *,
    job_id: int,
    expected_dispatch_generation: int,
    processor_name: str,
    processor_version: str,
    lease_seconds: int = 60,
) -> ClaimedProcessingJob | None:
    return _claim_processing_job(
        db,
        job_id=job_id,
        expected_dispatch_generation=expected_dispatch_generation,
        processor_name=processor_name,
        processor_version=processor_version,
        lease_seconds=lease_seconds,
        stage="scan",
        eligible_version_statuses=("received", "scanning"),
        version_status="scanning",
    )


def claim_parse_job_for_processing(
    db: Session,
    *,
    job_id: int,
    expected_dispatch_generation: int,
    processor_name: str,
    processor_version: str,
    lease_seconds: int = 60,
) -> ClaimedProcessingJob | None:
    return _claim_processing_job(
        db,
        job_id=job_id,
        expected_dispatch_generation=expected_dispatch_generation,
        processor_name=processor_name,
        processor_version=processor_version,
        lease_seconds=lease_seconds,
        stage="parse",
        eligible_version_statuses=("parsing",),
        version_status="parsing",
    )


def _claim_processing_job(
    db: Session,
    *,
    job_id: int,
    expected_dispatch_generation: int,
    processor_name: str,
    processor_version: str,
    stage: str,
    eligible_version_statuses: tuple[str, ...],
    version_status: str,
    lease_seconds: int = 60,
) -> ClaimedProcessingJob | None:
    company_id = db.info.get("tenant_company_id")
    if (
        isinstance(company_id, bool)
        or not isinstance(company_id, int)
        or company_id <= 0
    ):
        raise RuntimeError("processing job claim requires a tenant-scoped session")
    if isinstance(job_id, bool) or not isinstance(job_id, int) or job_id <= 0:
        raise ValueError("job_id must be a positive integer")
    if (
        isinstance(expected_dispatch_generation, bool)
        or not isinstance(expected_dispatch_generation, int)
        or expected_dispatch_generation <= 0
    ):
        raise ValueError("expected_dispatch_generation must be a positive integer")
    if not isinstance(processor_name, str):
        raise TypeError("processor_name must be a string")
    normalized_processor_name = processor_name.strip()
    if not normalized_processor_name or len(normalized_processor_name) > 64:
        raise ValueError("processor_name is invalid")
    if not isinstance(processor_version, str):
        raise TypeError("processor_version must be a string")
    normalized_processor_version = processor_version.strip()
    if not normalized_processor_version or len(normalized_processor_version) > 64:
        raise ValueError("processor_version is invalid")
    if (
        isinstance(lease_seconds, bool)
        or not isinstance(lease_seconds, int)
        or lease_seconds <= 0
    ):
        raise ValueError("lease_seconds must be a positive integer")
    now = datetime.now(timezone.utc)
    execution_id = str(uuid4())
    lease_expires_at = now + timedelta(seconds=lease_seconds)
    job = (
        db.execute(
            update(ArtifactProcessingJob)
            .where(
                ArtifactProcessingJob.id == job_id,
                ArtifactProcessingJob.stage == stage,
                ArtifactProcessingJob.status == "queued",
                ArtifactProcessingJob.available_at <= now,
                ArtifactProcessingJob.company_id == company_id,
                ArtifactProcessingJob.attempt_generation
                == expected_dispatch_generation - 1,
            )
            .values(
                status="running",
                attempt_generation=ArtifactProcessingJob.attempt_generation + 1,
                execution_id=execution_id,
                lease_expires_at=lease_expires_at,
            )
            .returning(
                ArtifactProcessingJob.id,
                ArtifactProcessingJob.company_id,
                ArtifactProcessingJob.artifact_version_id,
                ArtifactProcessingJob.attempt_generation,
                ArtifactProcessingJob.trace_request_id,
            )
            .execution_options(synchronize_session=False)
        )
        .mappings()
        .one_or_none()
    )
    if job is None:
        db.rollback()
        return None
    artifact_version_id = job["artifact_version_id"]
    generation = job["attempt_generation"]
    try:
        version_id = db.scalar(
            update(InputArtifactVersion)
            .where(
                InputArtifactVersion.id == job["artifact_version_id"],
                InputArtifactVersion.status.in_(eligible_version_statuses),
            )
            .values(
                status=version_status,
                status_changed_at=now,
            )
            .returning(InputArtifactVersion.id)
            .execution_options(synchronize_session=False)
        )
        if version_id is None:
            raise RuntimeError("processing job version is not claimable")
        attempt = ArtifactProcessingAttempt(
            artifact_version_id=artifact_version_id,
            stage=stage,
            processor_name=normalized_processor_name,
            processor_version=normalized_processor_version,
            attempt_number=generation,
            status="running",
            trace_id=job["trace_request_id"],
        )
        db.add(attempt)
        db.flush()
        db.commit()
        return ClaimedProcessingJob(
            company_id=job["company_id"],
            job_id=job["id"],
            artifact_version_id=artifact_version_id,
            generation=generation,
            trace_request_id=job["trace_request_id"],
            execution_id=execution_id,
        )
    except Exception:
        db.rollback()
        raise


def _scan_retry_delay_seconds(retry_count: int) -> int:
    if retry_count == 1:
        return 2
    if retry_count == 2:
        return 10
    raise ValueError("scan retry delay is not configured")


def recover_expired_scan_job(
    db: Session,
    *,
    job_id: int,
) -> ExpiredScanJobRecovery | None:
    company_id = db.info.get("tenant_company_id")
    if (
        isinstance(company_id, bool)
        or not isinstance(company_id, int)
        or company_id <= 0
    ):
        raise RuntimeError("scan job claim requires a tenant-scoped session")
    if isinstance(job_id, bool) or not isinstance(job_id, int) or job_id <= 0:
        raise ValueError("job_id must be a positive integer")
    now = datetime.now(timezone.utc)
    job = db.scalars(
        select(ArtifactProcessingJob)
        .where(
            ArtifactProcessingJob.id == job_id,
            ArtifactProcessingJob.stage == "scan",
            ArtifactProcessingJob.status == "running",
            ArtifactProcessingJob.lease_expires_at <= now,
            ArtifactProcessingJob.company_id == company_id,
        )
        .with_for_update(skip_locked=True)
    ).one_or_none()
    if job is None:
        return None
    attempt = db.scalars(
        select(ArtifactProcessingAttempt)
        .where(
            ArtifactProcessingAttempt.artifact_version_id == job.artifact_version_id,
            ArtifactProcessingAttempt.stage == "scan",
            ArtifactProcessingAttempt.attempt_number == job.attempt_generation,
            ArtifactProcessingAttempt.status == "running",
        )
        .with_for_update()
    ).one_or_none()
    if attempt is None:
        db.rollback()
        raise RuntimeError("expired scan job has no matching running attempt")
    version = db.scalars(
        select(InputArtifactVersion)
        .where(InputArtifactVersion.id == job.artifact_version_id)
        .with_for_update()
    ).one_or_none()
    if version is None:
        db.rollback()
        raise RuntimeError("expired scan job version does not exist")
    new_retry_count = job.retry_count + 1
    if new_retry_count < job.max_attempts:
        next_retry_at = now + timedelta(
            seconds=_scan_retry_delay_seconds(new_retry_count)
        )
        attempt.status = "failed"
        attempt.finished_at = now
        attempt.error_code = "worker_lease_expired"
        attempt.retry_disposition = "scheduled"
        attempt.next_retry_at = next_retry_at
        job.status = "queued"
        job.execution_id = None
        job.lease_expires_at = None
        job.retry_count = new_retry_count
        job.last_error_code = "worker_lease_expired"
        job.available_at = next_retry_at
        event = ArtifactProcessingOutboxEvent(
            company_id=company_id,
            job_id=job.id,
            event_type="artifact_processing_job.created",
            dispatch_generation=job.attempt_generation + 1,
            trace_request_id=job.trace_request_id,
        )
        db.add(event)
        db.commit()
        return ExpiredScanJobRecovery(
            outcome="requeued",
            dispatch_generation=event.dispatch_generation,
        )
    else:
        attempt.status = "failed"
        attempt.finished_at = now
        attempt.error_code = "worker_lease_expired"
        attempt.retry_disposition = "exhausted"
        attempt.next_retry_at = None

        job.status = "failed"
        job.retry_count = new_retry_count
        job.execution_id = None
        job.lease_expires_at = None
        job.last_error_code = "scan_retry_exhausted"
        job.finished_at = now

        version.status = "failed"
        version.status_reason_code = "scan_retry_exhausted"
        version.status_changed_at = now

        db.commit()
        return ExpiredScanJobRecovery(
            outcome="failed",
            dispatch_generation=None,
        )


def complete_scan_job_processing(
    db: Session,
    *,
    job_id: int,
    execution_id: str,
    expected_generation: int,
) -> bool:
    company_id = db.info.get("tenant_company_id")
    if (
        isinstance(company_id, bool)
        or not isinstance(company_id, int)
        or company_id <= 0
    ):
        raise RuntimeError("scan job completion requires a tenant-scoped session")
    if isinstance(job_id, bool) or not isinstance(job_id, int) or job_id <= 0:
        raise ValueError("job_id must be a positive integer")
    if not isinstance(execution_id, str):
        raise TypeError("execution_id must be a string")
    normalized_execution_id = execution_id.strip()
    if not normalized_execution_id or len(normalized_execution_id) > 36:
        raise ValueError("execution_id is invalid")
    if (
        isinstance(expected_generation, bool)
        or not isinstance(expected_generation, int)
        or expected_generation <= 0
    ):
        raise ValueError("expected_generation must be a positive integer")
    now = datetime.now(timezone.utc)
    job = (
        db.execute(
            update(ArtifactProcessingJob)
            .where(
                ArtifactProcessingJob.id == job_id,
                ArtifactProcessingJob.company_id == company_id,
                ArtifactProcessingJob.stage == "scan",
                ArtifactProcessingJob.status == "running",
                ArtifactProcessingJob.execution_id == normalized_execution_id,
                ArtifactProcessingJob.attempt_generation == expected_generation,
                ArtifactProcessingJob.lease_expires_at > now,
            )
            .values(
                status="succeeded",
                execution_id=None,
                lease_expires_at=None,
                last_error_code=None,
                finished_at=now,
            )
            .returning(
                ArtifactProcessingJob.id,
                ArtifactProcessingJob.company_id,
                ArtifactProcessingJob.artifact_version_id,
                ArtifactProcessingJob.attempt_generation,
                ArtifactProcessingJob.max_attempts,
                ArtifactProcessingJob.trace_request_id,
            )
            .execution_options(synchronize_session=False)
        )
        .mappings()
        .one_or_none()
    )

    if job is None:
        db.rollback()
        return False
    try:
        attempt_id = db.scalar(
            update(ArtifactProcessingAttempt)
            .where(
                ArtifactProcessingAttempt.artifact_version_id
                == job["artifact_version_id"],
                ArtifactProcessingAttempt.stage == "scan",
                ArtifactProcessingAttempt.attempt_number == job["attempt_generation"],
                ArtifactProcessingAttempt.status == "running",
            )
            .values(
                status="succeeded",
                finished_at=now,
                error_code=None,
                retry_disposition=None,
                next_retry_at=None,
            )
            .returning(ArtifactProcessingAttempt.id)
            .execution_options(synchronize_session=False)
        )
        if attempt_id is None:
            raise RuntimeError("scan completion has no matching running attempt")

        version_id = db.scalar(
            update(InputArtifactVersion)
            .where(
                InputArtifactVersion.id == job["artifact_version_id"],
                InputArtifactVersion.status == "scanning",
            )
            .values(
                status="parsing",
                status_reason_code=None,
                status_changed_at=now,
            )
            .returning(InputArtifactVersion.id)
            .execution_options(synchronize_session=False)
        )
        if version_id is None:
            raise RuntimeError("scan completion version is not in scanning state")

        parse_job = ArtifactProcessingJob(
            company_id=job["company_id"],
            artifact_version_id=job["artifact_version_id"],
            stage="parse",
            max_attempts=job["max_attempts"],
            trace_request_id=job["trace_request_id"],
        )
        db.add(parse_job)
        db.flush()
        db.add(
            ArtifactProcessingOutboxEvent(
                company_id=job["company_id"],
                job_id=parse_job.id,
                event_type="artifact_processing_job.created",
                dispatch_generation=1,
                trace_request_id=job["trace_request_id"],
            )
        )
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise


def complete_parse_job_processing(
    db: Session,
    *,
    job_id: int,
    execution_id: str,
    expected_generation: int,
    result_schema_version: str,
    manifest_object_key: str,
    manifest_sha256: str,
    extracted_text_object_key: str | None,
    extracted_text_sha256: str | None,
    extracted_text_char_count: int,
) -> bool:
    """Persist the current parse worker's immutable output and mark its version ready."""
    company_id = db.info.get("tenant_company_id")
    if (
        isinstance(company_id, bool)
        or not isinstance(company_id, int)
        or company_id <= 0
    ):
        raise RuntimeError("parse job completion requires a tenant-scoped session")
    if isinstance(job_id, bool) or not isinstance(job_id, int) or job_id <= 0:
        raise ValueError("job_id must be a positive integer")
    if not isinstance(execution_id, str):
        raise TypeError("execution_id must be a string")
    normalized_execution_id = execution_id.strip()
    if not normalized_execution_id or len(normalized_execution_id) > 36:
        raise ValueError("execution_id is invalid")
    if (
        isinstance(expected_generation, bool)
        or not isinstance(expected_generation, int)
        or expected_generation <= 0
    ):
        raise ValueError("expected_generation must be a positive integer")
    if not isinstance(result_schema_version, str):
        raise TypeError("result_schema_version must be a string")
    normalized_schema_version = result_schema_version.strip()
    if not normalized_schema_version or len(normalized_schema_version) > 64:
        raise ValueError("result_schema_version is invalid")
    if not isinstance(manifest_object_key, str):
        raise TypeError("manifest_object_key must be a string")
    normalized_manifest_object_key = manifest_object_key.strip()
    if not normalized_manifest_object_key or len(normalized_manifest_object_key) > 512:
        raise ValueError("manifest_object_key is invalid")
    if not isinstance(manifest_sha256, str):
        raise TypeError("manifest_sha256 must be a string")
    normalized_manifest_sha256 = manifest_sha256.strip()
    if not _SHA256_HEX_PATTERN.fullmatch(normalized_manifest_sha256):
        raise ValueError("manifest_sha256 must be a lowercase SHA-256 hex digest")
    if (
        isinstance(extracted_text_char_count, bool)
        or not isinstance(extracted_text_char_count, int)
        or extracted_text_char_count < 0
    ):
        raise ValueError("extracted_text_char_count must be a non-negative integer")
    if (extracted_text_object_key is None) != (extracted_text_sha256 is None):
        raise ValueError(
            "extracted text object key and SHA-256 must be provided together"
        )
    if extracted_text_object_key is None:
        if extracted_text_char_count != 0:
            raise ValueError("missing extracted text must have zero character count")
        normalized_text_object_key = None
        normalized_text_sha256 = None
    else:
        if not isinstance(extracted_text_object_key, str):
            raise TypeError("extracted_text_object_key must be a string or None")
        if not isinstance(extracted_text_sha256, str):
            raise TypeError("extracted_text_sha256 must be a string or None")
        normalized_text_object_key = extracted_text_object_key.strip()
        normalized_text_sha256 = extracted_text_sha256.strip()
        if not normalized_text_object_key or len(normalized_text_object_key) > 512:
            raise ValueError("extracted_text_object_key is invalid")
        if not _SHA256_HEX_PATTERN.fullmatch(normalized_text_sha256):
            raise ValueError(
                "extracted_text_sha256 must be a lowercase SHA-256 hex digest"
            )

    now = datetime.now(timezone.utc)
    job = (
        db.execute(
            update(ArtifactProcessingJob)
            .where(
                ArtifactProcessingJob.id == job_id,
                ArtifactProcessingJob.company_id == company_id,
                ArtifactProcessingJob.stage == "parse",
                ArtifactProcessingJob.status == "running",
                ArtifactProcessingJob.execution_id == normalized_execution_id,
                ArtifactProcessingJob.attempt_generation == expected_generation,
                ArtifactProcessingJob.lease_expires_at > now,
            )
            .values(
                status="succeeded",
                execution_id=None,
                lease_expires_at=None,
                last_error_code=None,
                finished_at=now,
            )
            .returning(
                ArtifactProcessingJob.artifact_version_id,
                ArtifactProcessingJob.attempt_generation,
            )
            .execution_options(synchronize_session=False)
        )
        .mappings()
        .one_or_none()
    )
    if job is None:
        db.rollback()
        return False

    try:
        attempt_id = db.scalar(
            update(ArtifactProcessingAttempt)
            .where(
                ArtifactProcessingAttempt.artifact_version_id
                == job["artifact_version_id"],
                ArtifactProcessingAttempt.stage == "parse",
                ArtifactProcessingAttempt.attempt_number == job["attempt_generation"],
                ArtifactProcessingAttempt.status == "running",
            )
            .values(
                status="succeeded",
                finished_at=now,
                error_code=None,
                retry_disposition=None,
                next_retry_at=None,
            )
            .returning(ArtifactProcessingAttempt.id)
            .execution_options(synchronize_session=False)
        )
        if attempt_id is None:
            raise RuntimeError("parse completion has no matching running attempt")

        result = ArtifactParseResult(
            artifact_version_id=job["artifact_version_id"],
            processing_attempt_id=attempt_id,
            result_schema_version=normalized_schema_version,
            manifest_object_key=normalized_manifest_object_key,
            manifest_sha256=normalized_manifest_sha256,
            extracted_text_object_key=normalized_text_object_key,
            extracted_text_sha256=normalized_text_sha256,
            extracted_text_char_count=extracted_text_char_count,
        )
        db.add(result)
        db.flush()

        version_id = db.scalar(
            update(InputArtifactVersion)
            .where(
                InputArtifactVersion.id == job["artifact_version_id"],
                InputArtifactVersion.status == "parsing",
            )
            .values(
                active_parse_result_id=result.id,
                status="ready",
                status_reason_code=None,
                status_changed_at=now,
            )
            .returning(InputArtifactVersion.id)
            .execution_options(synchronize_session=False)
        )
        if version_id is None:
            raise RuntimeError("parse completion version is not in parsing state")

        db.commit()
        return True
    except Exception:
        db.rollback()
        raise


def fail_parse_job_processing(
    db: Session,
    *,
    job_id: int,
    execution_id: str,
    expected_generation: int,
    error_code: str,
) -> bool:
    """Record a non-retryable parse failure owned by the current worker."""
    company_id = db.info.get("tenant_company_id")
    if (
        isinstance(company_id, bool)
        or not isinstance(company_id, int)
        or company_id <= 0
    ):
        raise RuntimeError("parse job failure requires a tenant-scoped session")
    if isinstance(job_id, bool) or not isinstance(job_id, int) or job_id <= 0:
        raise ValueError("job_id must be a positive integer")
    if not isinstance(execution_id, str):
        raise TypeError("execution_id must be a string")
    normalized_execution_id = execution_id.strip()
    if not normalized_execution_id or len(normalized_execution_id) > 36:
        raise ValueError("execution_id is invalid")
    if (
        isinstance(expected_generation, bool)
        or not isinstance(expected_generation, int)
        or expected_generation <= 0
    ):
        raise ValueError("expected_generation must be a positive integer")
    if not isinstance(error_code, str):
        raise TypeError("error_code must be a string")
    normalized_error_code = error_code.strip()
    if not normalized_error_code or len(normalized_error_code) > 64:
        raise ValueError("error_code is invalid")

    now = datetime.now(timezone.utc)
    job = (
        db.execute(
            update(ArtifactProcessingJob)
            .where(
                ArtifactProcessingJob.id == job_id,
                ArtifactProcessingJob.company_id == company_id,
                ArtifactProcessingJob.stage == "parse",
                ArtifactProcessingJob.status == "running",
                ArtifactProcessingJob.execution_id == normalized_execution_id,
                ArtifactProcessingJob.attempt_generation == expected_generation,
                ArtifactProcessingJob.lease_expires_at > now,
            )
            .values(
                status="failed",
                execution_id=None,
                lease_expires_at=None,
                last_error_code=normalized_error_code,
                finished_at=now,
            )
            .returning(
                ArtifactProcessingJob.artifact_version_id,
                ArtifactProcessingJob.attempt_generation,
            )
            .execution_options(synchronize_session=False)
        )
        .mappings()
        .one_or_none()
    )
    if job is None:
        db.rollback()
        return False

    try:
        attempt_id = db.scalar(
            update(ArtifactProcessingAttempt)
            .where(
                ArtifactProcessingAttempt.artifact_version_id
                == job["artifact_version_id"],
                ArtifactProcessingAttempt.stage == "parse",
                ArtifactProcessingAttempt.attempt_number == job["attempt_generation"],
                ArtifactProcessingAttempt.status == "running",
            )
            .values(
                status="failed",
                finished_at=now,
                error_code=normalized_error_code,
                retry_disposition="not_retryable",
                next_retry_at=None,
            )
            .returning(ArtifactProcessingAttempt.id)
            .execution_options(synchronize_session=False)
        )
        if attempt_id is None:
            raise RuntimeError("parse failure has no matching running attempt")

        version_id = db.scalar(
            update(InputArtifactVersion)
            .where(
                InputArtifactVersion.id == job["artifact_version_id"],
                InputArtifactVersion.status == "parsing",
            )
            .values(
                status="failed",
                status_reason_code=normalized_error_code,
                status_changed_at=now,
            )
            .returning(InputArtifactVersion.id)
            .execution_options(synchronize_session=False)
        )
        if version_id is None:
            raise RuntimeError("parse failure version is not in parsing state")

        db.commit()
        return True
    except Exception:
        db.rollback()
        raise


def reject_scan_job_processing(
    db: Session,
    *,
    job_id: int,
    execution_id: str,
    expected_generation: int,
    reason_code: str,
) -> bool:
    """Record a final security-policy rejection owned by the current scanner."""
    company_id = db.info.get("tenant_company_id")
    if (
        isinstance(company_id, bool)
        or not isinstance(company_id, int)
        or company_id <= 0
    ):
        raise RuntimeError("scan job rejection requires a tenant-scoped session")
    if isinstance(job_id, bool) or not isinstance(job_id, int) or job_id <= 0:
        raise ValueError("job_id must be a positive integer")
    if not isinstance(execution_id, str):
        raise TypeError("execution_id must be a string")
    normalized_execution_id = execution_id.strip()
    if not normalized_execution_id or len(normalized_execution_id) > 36:
        raise ValueError("execution_id is invalid")
    if (
        isinstance(expected_generation, bool)
        or not isinstance(expected_generation, int)
        or expected_generation <= 0
    ):
        raise ValueError("expected_generation must be a positive integer")
    if not isinstance(reason_code, str):
        raise TypeError("reason_code must be a string")
    normalized_reason_code = reason_code.strip()
    if not normalized_reason_code or len(normalized_reason_code) > 64:
        raise ValueError("reason_code is invalid")

    now = datetime.now(timezone.utc)
    job = (
        db.execute(
            update(ArtifactProcessingJob)
            .where(
                ArtifactProcessingJob.id == job_id,
                ArtifactProcessingJob.company_id == company_id,
                ArtifactProcessingJob.stage == "scan",
                ArtifactProcessingJob.status == "running",
                ArtifactProcessingJob.execution_id == normalized_execution_id,
                ArtifactProcessingJob.attempt_generation == expected_generation,
                ArtifactProcessingJob.lease_expires_at > now,
            )
            .values(
                status="rejected",
                execution_id=None,
                lease_expires_at=None,
                last_error_code=normalized_reason_code,
                finished_at=now,
            )
            .returning(
                ArtifactProcessingJob.artifact_version_id,
                ArtifactProcessingJob.attempt_generation,
            )
            .execution_options(synchronize_session=False)
        )
        .mappings()
        .one_or_none()
    )
    if job is None:
        db.rollback()
        return False

    try:
        attempt_id = db.scalar(
            update(ArtifactProcessingAttempt)
            .where(
                ArtifactProcessingAttempt.artifact_version_id
                == job["artifact_version_id"],
                ArtifactProcessingAttempt.stage == "scan",
                ArtifactProcessingAttempt.attempt_number == job["attempt_generation"],
                ArtifactProcessingAttempt.status == "running",
            )
            .values(
                status="rejected",
                finished_at=now,
                error_code=normalized_reason_code,
                retry_disposition=None,
                next_retry_at=None,
            )
            .returning(ArtifactProcessingAttempt.id)
            .execution_options(synchronize_session=False)
        )
        if attempt_id is None:
            raise RuntimeError("scan rejection has no matching running attempt")

        version_id = db.scalar(
            update(InputArtifactVersion)
            .where(
                InputArtifactVersion.id == job["artifact_version_id"],
                InputArtifactVersion.status == "scanning",
            )
            .values(
                status="rejected",
                status_reason_code=normalized_reason_code,
                status_changed_at=now,
            )
            .returning(InputArtifactVersion.id)
            .execution_options(synchronize_session=False)
        )
        if version_id is None:
            raise RuntimeError("scan rejection version is not in scanning state")

        db.commit()
        return True
    except Exception:
        db.rollback()
        raise


def fail_scan_job_processing(
    db: Session,
    *,
    job_id: int,
    execution_id: str,
    expected_generation: int,
    error_code: str,
    retryable: bool,
) -> ScanJobFailureOutcome | None:
    """Record the current scanner failure and schedule its bounded retry if allowed."""
    company_id = db.info.get("tenant_company_id")
    if (
        isinstance(company_id, bool)
        or not isinstance(company_id, int)
        or company_id <= 0
    ):
        raise RuntimeError("scan job failure requires a tenant-scoped session")
    if isinstance(job_id, bool) or not isinstance(job_id, int) or job_id <= 0:
        raise ValueError("job_id must be a positive integer")
    if not isinstance(execution_id, str):
        raise TypeError("execution_id must be a string")
    normalized_execution_id = execution_id.strip()
    if not normalized_execution_id or len(normalized_execution_id) > 36:
        raise ValueError("execution_id is invalid")
    if (
        isinstance(expected_generation, bool)
        or not isinstance(expected_generation, int)
        or expected_generation <= 0
    ):
        raise ValueError("expected_generation must be a positive integer")
    if not isinstance(error_code, str):
        raise TypeError("error_code must be a string")
    normalized_error_code = error_code.strip()
    if not normalized_error_code or len(normalized_error_code) > 64:
        raise ValueError("error_code is invalid")
    if not isinstance(retryable, bool):
        raise TypeError("retryable must be a boolean")

    now = datetime.now(timezone.utc)
    job = db.scalars(
        select(ArtifactProcessingJob)
        .where(
            ArtifactProcessingJob.id == job_id,
            ArtifactProcessingJob.company_id == company_id,
            ArtifactProcessingJob.stage == "scan",
            ArtifactProcessingJob.status == "running",
            ArtifactProcessingJob.execution_id == normalized_execution_id,
            ArtifactProcessingJob.attempt_generation == expected_generation,
            ArtifactProcessingJob.lease_expires_at > now,
        )
        .with_for_update()
    ).one_or_none()
    if job is None:
        db.rollback()
        return None

    try:
        attempt = db.scalars(
            select(ArtifactProcessingAttempt)
            .where(
                ArtifactProcessingAttempt.artifact_version_id
                == job.artifact_version_id,
                ArtifactProcessingAttempt.stage == "scan",
                ArtifactProcessingAttempt.attempt_number == job.attempt_generation,
                ArtifactProcessingAttempt.status == "running",
            )
            .with_for_update()
        ).one_or_none()
        if attempt is None:
            raise RuntimeError("scan failure has no matching running attempt")
        version = db.scalars(
            select(InputArtifactVersion)
            .where(
                InputArtifactVersion.id == job.artifact_version_id,
                InputArtifactVersion.status == "scanning",
            )
            .with_for_update()
        ).one_or_none()
        if version is None:
            raise RuntimeError("scan failure version is not in scanning state")

        new_retry_count = job.retry_count + 1
        if retryable and new_retry_count < job.max_attempts:
            next_retry_at = now + timedelta(
                seconds=_scan_retry_delay_seconds(new_retry_count)
            )
            attempt.status = "failed"
            attempt.finished_at = now
            attempt.error_code = normalized_error_code
            attempt.retry_disposition = "scheduled"
            attempt.next_retry_at = next_retry_at
            job.status = "queued"
            job.execution_id = None
            job.lease_expires_at = None
            job.retry_count = new_retry_count
            job.last_error_code = normalized_error_code
            job.available_at = next_retry_at
            event = ArtifactProcessingOutboxEvent(
                company_id=company_id,
                job_id=job.id,
                event_type="artifact_processing_job.created",
                dispatch_generation=job.attempt_generation + 1,
                trace_request_id=job.trace_request_id,
            )
            db.add(event)
            db.commit()
            return ScanJobFailureOutcome("requeued", event.dispatch_generation)

        terminal_error_code = (
            "scan_retry_exhausted" if retryable else normalized_error_code
        )
        attempt.status = "failed"
        attempt.finished_at = now
        attempt.error_code = normalized_error_code
        attempt.retry_disposition = "exhausted" if retryable else "not_retryable"
        attempt.next_retry_at = None
        job.status = "failed"
        job.execution_id = None
        job.lease_expires_at = None
        job.retry_count = new_retry_count
        job.last_error_code = terminal_error_code
        job.finished_at = now
        version.status = "failed"
        version.status_reason_code = terminal_error_code
        version.status_changed_at = now
        db.commit()
        return ScanJobFailureOutcome("failed", None)
    except Exception:
        db.rollback()
        raise
