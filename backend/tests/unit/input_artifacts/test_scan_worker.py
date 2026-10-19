from pathlib import Path

from app.db.session import set_tenant_scope
from app.modules.identity.models import User
from app.modules.input_artifacts.models import ArtifactProcessingJob, InputArtifactVersion
from app.modules.input_artifacts.processing.processing_storage import StoredProcessingObject
from app.modules.input_artifacts.processing.scan_worker import execute_scan_job
from app.modules.input_artifacts.processing.scanner import ScanResult
from app.modules.input_artifacts.versions import create_received_input_artifact_version
from app.modules.organizations.models import Company, CompanyMember
from sqlalchemy.orm import Session


class _Storage:
    def download_quarantine_object(self, *, object_key: str, destination_path: Path):
        destination_path.write_bytes(b"safe")
        return StoredProcessingObject(object_key, 1024, "a" * 64)


class _CleanScanner:
    processor_name = "clamd"

    def scan_file(self, _path: Path) -> ScanResult:
        return ScanResult("clean")


def test_scan_worker_claims_then_schedules_parse_after_a_clean_scan(
    db_session: Session,
    test_user: User,
) -> None:
    company = Company(name="scan-worker-company")
    db_session.add(company)
    db_session.flush()
    db_session.add(
        CompanyMember(
            company_id=company.id,
            user_id=test_user.id,
            role="analyst",
            status="approved",
        )
    )
    db_session.flush()
    set_tenant_scope(db_session, company.id)
    version = create_received_input_artifact_version(
        db_session,
        company_id=company.id,
        uploaded_by_user_id=test_user.id,
        kind="attachment",
        original_filename="sales.csv",
        raw_object_key="input-artifacts/quarantine/7/session/payload",
        byte_size=1024,
        sha256="a" * 64,
        commit=False,
    )
    job = ArtifactProcessingJob(
        company_id=company.id,
        artifact_version_id=version.id,
        stage="scan",
        trace_request_id="trace-scan-worker-clean",
    )
    db_session.add(job)
    db_session.commit()

    assert execute_scan_job(
        db_session,
        job_id=job.id,
        dispatch_generation=1,
        processor_name="clamd",
        processor_version="1.0.0",
        scanner_factory=_CleanScanner,  # type: ignore[arg-type]
        storage_factory=_Storage,  # type: ignore[arg-type]
    )

    db_session.refresh(job)
    db_session.refresh(version)
    assert job.status == "succeeded"
    assert version.status == "parsing"
    assert (
        db_session.query(ArtifactProcessingJob)
        .filter_by(artifact_version_id=version.id, stage="parse")
        .count()
        == 1
    )
