from datetime import datetime, timezone

import pytest
from app.db.session import set_tenant_scope
from app.modules.identity.models import User
from app.modules.input_artifacts.models import (
    ArtifactParseResult,
    ArtifactProcessingAttempt,
    InputArtifactVersion,
)
from app.modules.input_artifacts.versions import create_received_input_artifact_version
from app.modules.organizations.models import Company, CompanyMember
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


def _company_scope(db: Session, user: User, *, name: str) -> Company:
    company = Company(name=name)
    db.add(company)
    db.flush()
    db.add(
        CompanyMember(
            company_id=company.id,
            user_id=user.id,
            role="analyst",
            status="approved",
        )
    )
    db.flush()
    set_tenant_scope(db, company.id)
    return company


def _parse_attempt(
    db: Session,
    *,
    company: Company,
    user: User,
    suffix: str,
) -> tuple[InputArtifactVersion, ArtifactProcessingAttempt]:
    version = create_received_input_artifact_version(
        db,
        company_id=company.id,
        uploaded_by_user_id=user.id,
        kind="attachment",
        original_filename=f"sales-{suffix}.csv",
        raw_object_key=f"input-artifacts/quarantine/{company.id}/sales-{suffix}.csv",
        byte_size=1024,
        sha256="a" * 64,
        commit=False,
    )
    version.status = "parsing"
    attempt = ArtifactProcessingAttempt(
        artifact_version_id=version.id,
        stage="parse",
        attempt_number=1,
        status="succeeded",
        processor_name="document-parser",
        processor_version="2.0.0",
        trace_id=f"trace-parse-result-{suffix}",
        finished_at=datetime.now(timezone.utc),
    )
    db.add(attempt)
    db.flush()
    return version, attempt


def _parse_result(
    *,
    version: InputArtifactVersion,
    attempt: ArtifactProcessingAttempt,
    suffix: str,
) -> ArtifactParseResult:
    return ArtifactParseResult(
        artifact_version_id=version.id,
        processing_attempt_id=attempt.id,
        result_schema_version="artifact-parse-result/v1",
        manifest_object_key=f"input-artifacts/parsed/{suffix}/manifest.json",
        manifest_sha256="b" * 64,
        extracted_text_object_key=f"input-artifacts/parsed/{suffix}/text.txt",
        extracted_text_sha256="c" * 64,
        extracted_text_char_count=24,
    )


def test_parse_result_can_become_its_own_version_active_result(
    db_session: Session,
    test_user: User,
) -> None:
    company = _company_scope(db_session, test_user, name="parse-result-company")
    version, attempt = _parse_attempt(
        db_session,
        company=company,
        user=test_user,
        suffix="valid",
    )
    result = _parse_result(version=version, attempt=attempt, suffix="valid")
    db_session.add(result)
    db_session.flush()

    version.active_parse_result_id = result.id
    db_session.flush()

    assert result.processing_attempt_id == attempt.id
    assert version.active_parse_result_id == result.id


def test_parse_result_cannot_reference_an_attempt_from_another_version(
    db_session: Session,
    test_user: User,
) -> None:
    company = _company_scope(
        db_session,
        test_user,
        name="parse-result-attempt-scope-company",
    )
    _, first_attempt = _parse_attempt(
        db_session,
        company=company,
        user=test_user,
        suffix="first",
    )
    second_version, _ = _parse_attempt(
        db_session,
        company=company,
        user=test_user,
        suffix="second",
    )
    invalid_result = ArtifactParseResult(
        artifact_version_id=second_version.id,
        processing_attempt_id=first_attempt.id,
        result_schema_version="artifact-parse-result/v1",
        manifest_object_key="input-artifacts/parsed/invalid/manifest.json",
        manifest_sha256="b" * 64,
        extracted_text_char_count=0,
    )

    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(invalid_result)
        db_session.flush()


def test_version_cannot_activate_a_parse_result_from_another_version(
    db_session: Session,
    test_user: User,
) -> None:
    company = _company_scope(
        db_session,
        test_user,
        name="parse-result-active-scope-company",
    )
    first_version, first_attempt = _parse_attempt(
        db_session,
        company=company,
        user=test_user,
        suffix="first",
    )
    second_version, _ = _parse_attempt(
        db_session,
        company=company,
        user=test_user,
        suffix="second",
    )
    first_result = _parse_result(
        version=first_version,
        attempt=first_attempt,
        suffix="first",
    )
    db_session.add(first_result)
    db_session.flush()

    second_version.active_parse_result_id = first_result.id
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.flush()


def test_parse_result_is_hidden_when_the_tenant_scope_changes(
    db_session: Session,
    test_user: User,
) -> None:
    first_company = _company_scope(
        db_session,
        test_user,
        name="parse-result-rls-first-company",
    )
    version, attempt = _parse_attempt(
        db_session,
        company=first_company,
        user=test_user,
        suffix="rls",
    )
    result = _parse_result(version=version, attempt=attempt, suffix="rls")
    db_session.add(result)
    db_session.commit()
    result_id = result.id

    second_company = Company(name="parse-result-rls-second-company")
    db_session.add(second_company)
    db_session.flush()
    db_session.expunge_all()
    set_tenant_scope(db_session, second_company.id)

    visible_result = db_session.scalar(
        select(ArtifactParseResult).where(ArtifactParseResult.id == result_id)
    )

    assert visible_result is None
