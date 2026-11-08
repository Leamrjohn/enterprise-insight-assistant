import pytest
from app.db.session import set_tenant_scope
from app.modules.identity.models import User
from app.modules.input_artifacts.models import InputArtifact, InputArtifactVersion
from app.modules.input_artifacts.versions import (
    create_received_input_artifact_version,
)
from app.modules.organizations.models import Company
from sqlalchemy.orm import Session


def _create_company_and_scope(db: Session, user: User) -> Company:
    company = Company(name="input-artifact-service-company")
    db.add(company)
    db.flush()
    set_tenant_scope(db, company.id)
    return company


def test_create_received_input_artifact_version_persists_root_and_version(
    db_session: Session,
    test_user: User,
) -> None:
    company = _create_company_and_scope(db_session, test_user)

    version = create_received_input_artifact_version(
        db_session,
        company_id=company.id,
        uploaded_by_user_id=test_user.id,
        kind="dataset",
        original_filename="C:\\fakepath\\Sales.CSV",
        raw_object_key="raw/company-1/upload-1",
        byte_size=12,
        sha256="a" * 64,
        declared_mime_type=" text/csv ",
    )

    artifact = db_session.get(InputArtifact, version.artifact_id)
    stored_version = db_session.get(InputArtifactVersion, version.id)

    assert artifact is not None
    assert artifact.company_id == company.id
    assert artifact.uploaded_by_user_id == test_user.id
    assert artifact.kind == "dataset"
    assert stored_version is not None
    assert stored_version.version_number == 1
    assert stored_version.status == "received"
    assert stored_version.original_filename == "Sales.CSV"
    assert stored_version.declared_extension == "csv"
    assert stored_version.declared_mime_type == "text/csv"
    assert stored_version.detected_mime_type is None


def test_invalid_sha256_does_not_create_a_partial_artifact(
    db_session: Session,
    test_user: User,
) -> None:
    company = _create_company_and_scope(db_session, test_user)

    with pytest.raises(ValueError, match="sha256"):
        create_received_input_artifact_version(
            db_session,
            company_id=company.id,
            uploaded_by_user_id=test_user.id,
            kind="attachment",
            original_filename="report.pdf",
            raw_object_key="raw/company-1/upload-invalid",
            byte_size=12,
            sha256="not-a-sha256",
        )

    assert db_session.query(InputArtifact).count() == 0
    assert db_session.query(InputArtifactVersion).count() == 0


def test_create_received_input_artifact_version_can_defer_commit(
    db_session: Session,
    test_user: User,
    monkeypatch,
) -> None:
    company = _create_company_and_scope(db_session, test_user)

    def fail_if_commit_is_called() -> None:
        raise AssertionError("commit must be owned by the caller")

    monkeypatch.setattr(db_session, "commit", fail_if_commit_is_called)

    version = create_received_input_artifact_version(
        db_session,
        company_id=company.id,
        uploaded_by_user_id=test_user.id,
        kind="attachment",
        original_filename="report.pdf",
        raw_object_key="raw/company-1/deferred-commit",
        byte_size=12,
        sha256="b" * 64,
        commit=False,
    )

    assert version.id is not None
    assert db_session.get(InputArtifactVersion, version.id) is not None
