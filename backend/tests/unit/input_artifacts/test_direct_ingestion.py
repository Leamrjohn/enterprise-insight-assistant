from io import BytesIO

import pytest
from app.core.settings import get_settings
from app.db.session import set_tenant_scope
from app.modules.identity.models import User
from app.modules.input_artifacts.models import InputArtifact, InputArtifactVersion
from app.modules.input_artifacts.upload.direct_ingestion import (
    ingest_received_input_artifact,
)
from app.modules.organizations.models import Company
from sqlalchemy.orm import Session


def _create_company_and_scope(db: Session) -> Company:
    company = Company(name="input-artifact-ingestion-company")
    db.add(company)
    db.flush()
    set_tenant_scope(db, company.id)
    return company


def test_ingest_received_input_artifact_keeps_quarantine_file_after_persisting(
    db_session: Session,
    test_user: User,
    tmp_path,
) -> None:
    company = _create_company_and_scope(db_session)
    settings = get_settings().model_copy(update={"storage_dir": tmp_path})

    version = ingest_received_input_artifact(
        db_session,
        company_id=company.id,
        uploaded_by_user_id=test_user.id,
        kind="dataset",
        file_stream=BytesIO(b"region,sales\neast,10\n"),
        original_filename="sales.csv",
        settings=settings,
        declared_mime_type="text/csv",
    )

    artifact = db_session.get(InputArtifact, version.artifact_id)
    stored_version = db_session.get(InputArtifactVersion, version.id)
    assert artifact is not None
    assert stored_version is not None
    assert (
        settings.storage_dir / version.raw_object_key
    ).read_bytes() == b"region,sales\neast,10\n"


def test_ingest_removes_new_quarantine_file_when_database_persistence_fails(
    db_session: Session,
    test_user: User,
    tmp_path,
) -> None:
    company = _create_company_and_scope(db_session)
    settings = get_settings().model_copy(update={"storage_dir": tmp_path})

    with pytest.raises(ValueError, match="kind is invalid"):
        ingest_received_input_artifact(
            db_session,
            company_id=company.id,
            uploaded_by_user_id=test_user.id,
            kind="not-a-kind",
            file_stream=BytesIO(b"quarterly report"),
            original_filename="report.txt",
            settings=settings,
        )

    assert db_session.query(InputArtifact).count() == 0
    assert db_session.query(InputArtifactVersion).count() == 0
    assert list(settings.input_artifact_quarantine_dir.iterdir()) == []
