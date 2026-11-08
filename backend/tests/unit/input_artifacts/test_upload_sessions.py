from datetime import datetime, timedelta, timezone

import pytest
from app.db.session import set_tenant_scope
from app.modules.conversations.models import Conversation
from app.modules.identity.models import User
from app.modules.input_artifacts.models import InputArtifactUploadSession
from app.modules.organizations.models import Company, CompanyMember
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


def _create_conversation_scope(
    db: Session,
    user: User,
) -> tuple[Company, Conversation]:
    company = Company(name="input-artifact-upload-session-company")
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
    conversation = Conversation(
        user_id=user.id,
        company_id=company.id,
        title="Upload session test conversation",
    )
    db.add(conversation)
    db.flush()
    set_tenant_scope(db, company.id)
    return company, conversation


def _new_session(
    *,
    company: Company,
    user: User,
    conversation: Conversation,
    idempotency_key: str = "attachment-upload-1",
) -> InputArtifactUploadSession:
    return InputArtifactUploadSession(
        company_id=company.id,
        submitted_by_user_id=user.id,
        conversation_id=conversation.id,
        idempotency_key=idempotency_key,
        request_fingerprint="a" * 64,
        client_filename="sales-report.xlsx",
        client_reported_byte_size=1024,
        client_reported_mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        client_reported_sha256="b" * 64,
        upload_policy_version="conversation-attachment-v1",
        storage_provider="object-storage",
        staging_object_key=f"quarantine/{idempotency_key}",
        upload_expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
        trace_request_id="trace-upload-session-1",
    )


def test_upload_session_starts_as_server_owned_awaiting_upload_record(
    db_session: Session,
    test_user: User,
) -> None:
    company, conversation = _create_conversation_scope(db_session, test_user)
    session = _new_session(
        company=company,
        user=test_user,
        conversation=conversation,
    )
    db_session.add(session)
    db_session.flush()

    assert session.public_id
    assert session.status == "awaiting_upload"
    assert session.finalization_generation == 0
    assert session.finalization_execution_id is None
    assert session.finalization_lease_expires_at is None
    assert session.storage_verified_byte_size is None
    assert session.storage_verified_sha256 is None
    assert session.artifact_version_id is None
    assert session.client_reported_sha256 == "b" * 64


def test_upload_session_rejects_completed_state_without_verified_object_and_version(
    db_session: Session,
    test_user: User,
) -> None:
    company, conversation = _create_conversation_scope(db_session, test_user)
    session = _new_session(
        company=company,
        user=test_user,
        conversation=conversation,
    )
    session.status = "completed"
    session.finalization_generation = 1
    session.finished_at = datetime.now(timezone.utc)
    db_session.add(session)

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_upload_session_idempotency_key_is_unique_within_its_request_scope(
    db_session: Session,
    test_user: User,
) -> None:
    company, conversation = _create_conversation_scope(db_session, test_user)
    first = _new_session(
        company=company,
        user=test_user,
        conversation=conversation,
    )
    db_session.add(first)
    db_session.flush()

    duplicate = _new_session(
        company=company,
        user=test_user,
        conversation=conversation,
    )
    duplicate.staging_object_key = "quarantine/another-object"
    db_session.add(duplicate)

    with pytest.raises(IntegrityError):
        db_session.flush()
