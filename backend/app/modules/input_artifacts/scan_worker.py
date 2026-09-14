"""One claimed scan-job execution, independent of the Celery transport."""

from pathlib import Path
from tempfile import TemporaryDirectory
from collections.abc import Callable

from app.modules.input_artifacts.models import InputArtifactVersion
from app.modules.input_artifacts.processing_jobs import (
    claim_scan_job_for_processing,
    complete_scan_job_processing,
    fail_scan_job_processing,
    reject_scan_job_processing,
)
from app.modules.input_artifacts.processing_storage import (
    ArtifactProcessingObjectNotFoundError,
    ArtifactProcessingStorage,
    ArtifactProcessingStorageUnavailableError,
)
from app.modules.input_artifacts.scanner import ClamDScanner
from sqlalchemy.orm import Session


def execute_scan_job(
    db: Session,
    *,
    job_id: int,
    dispatch_generation: int,
    processor_name: str,
    processor_version: str,
    scanner_factory: Callable[[], ClamDScanner],
    storage_factory: Callable[[], ArtifactProcessingStorage],
) -> bool:
    """Claim, download, verify, scan, and persist exactly one scan outcome."""
    claim = claim_scan_job_for_processing(
        db,
        job_id=job_id,
        expected_dispatch_generation=dispatch_generation,
        processor_name=processor_name,
        processor_version=processor_version,
    )
    if claim is None:
        return False
    try:
        scanner = scanner_factory()
        storage = storage_factory()
    except Exception:
        return _fail_retryable(db, claim, "processor_configuration_unavailable")
    version = db.get(InputArtifactVersion, claim.artifact_version_id)
    if version is None:
        raise RuntimeError("claimed scan job version is not visible")

    try:
        with TemporaryDirectory(prefix="artifact-scan-") as temporary_directory:
            local_path = Path(temporary_directory) / "raw-input"
            downloaded = storage.download_quarantine_object(
                object_key=version.raw_object_key,
                destination_path=local_path,
            )
            if downloaded.byte_size != version.byte_size or downloaded.sha256_hex != version.sha256:
                return reject_scan_job_processing(
                    db,
                    job_id=claim.job_id,
                    execution_id=claim.execution_id,
                    expected_generation=claim.generation,
                    reason_code="object_integrity_mismatch",
                )
            scan = scanner.scan_file(local_path)
    except ArtifactProcessingObjectNotFoundError:
        return _fail_non_retryable(db, claim, "quarantine_object_missing")
    except ArtifactProcessingStorageUnavailableError:
        return _fail_retryable(db, claim, "object_storage_unavailable")

    if scan.disposition == "clean":
        return complete_scan_job_processing(
            db,
            job_id=claim.job_id,
            execution_id=claim.execution_id,
            expected_generation=claim.generation,
        )
    if scan.disposition == "rejected":
        return reject_scan_job_processing(
            db,
            job_id=claim.job_id,
            execution_id=claim.execution_id,
            expected_generation=claim.generation,
            reason_code=scan.reason_code or "scanner_rejected",
        )
    _fail_retryable(db, claim, scan.reason_code or "scanner_failed")
    return True


def _fail_retryable(db: Session, claim, error_code: str) -> bool:
    return (
        fail_scan_job_processing(
            db,
            job_id=claim.job_id,
            execution_id=claim.execution_id,
            expected_generation=claim.generation,
            error_code=error_code,
            retryable=True,
        )
        is not None
    )


def _fail_non_retryable(db: Session, claim, error_code: str) -> bool:
    return (
        fail_scan_job_processing(
            db,
            job_id=claim.job_id,
            execution_id=claim.execution_id,
            expected_generation=claim.generation,
            error_code=error_code,
            retryable=False,
        )
        is not None
    )
