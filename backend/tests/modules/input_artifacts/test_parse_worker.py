from pathlib import Path

from app.db.session import set_tenant_scope
from app.modules.identity.models import User
from app.modules.input_artifacts.models import (
    ArtifactParseResult,
    ArtifactProcessingJob,
)
from app.modules.input_artifacts.parse_worker import execute_parse_job
from app.modules.input_artifacts.processing_storage import StoredProcessingObject
from app.modules.input_artifacts.versions import create_received_input_artifact_version
from app.modules.organizations.models import Company, CompanyMember
from sqlalchemy.orm import Session


class _Storage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def download_quarantine_object(self, *, object_key: str, destination_path: Path):
        content = b"region,sales\neast,10\nwest,=SUM(B2:B2)\n"
        destination_path.write_bytes(content)
        return StoredProcessingObject(
            object_key,
            len(content),
            "d1328f05cc06e76e429c15ebc2e5bb9635e77bbeebba9e23523323f319e2b386",
        )

    def write_parsed_object(self, *, object_key: str, content: bytes, content_type: str):
        self.objects[object_key] = content
        return StoredProcessingObject(
            object_key,
            len(content),
            __import__("hashlib").sha256(content).hexdigest(),
        )

    def write_parsed_file(self, *, object_key: str, source_path: Path, content_type: str):
        content = source_path.read_bytes()
        return self.write_parsed_object(
            object_key=object_key,
            content=content,
            content_type=content_type,
        )


def test_parse_worker_persists_immutable_csv_output_and_marks_version_ready(
    db_session: Session,
    test_user: User,
) -> None:
    company = Company(name="parse-worker-company")
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
        byte_size=38,
        sha256="d1328f05cc06e76e429c15ebc2e5bb9635e77bbeebba9e23523323f319e2b386",
        commit=False,
    )
    version.status = "parsing"
    parse_job = ArtifactProcessingJob(
        company_id=company.id,
        artifact_version_id=version.id,
        stage="parse",
        trace_request_id="trace-parse-worker-clean",
    )
    db_session.add(parse_job)
    db_session.commit()
    storage = _Storage()

    assert execute_parse_job(
        db_session,
        job_id=parse_job.id,
        dispatch_generation=1,
        processor_name="builtin-text-csv",
        processor_version="1.0.0",
        storage_factory=lambda: storage,  # type: ignore[arg-type]
    )

    db_session.refresh(parse_job)
    db_session.refresh(version)
    result = db_session.query(ArtifactParseResult).one()
    assert parse_job.status == "succeeded"
    assert version.status == "ready"
    assert version.active_parse_result_id == result.id
    assert result.manifest_object_key in storage.objects
    assert result.extracted_text_object_key in storage.objects
    assert b'"formula_execution":"not_performed"' in storage.objects[
        result.manifest_object_key
    ]
