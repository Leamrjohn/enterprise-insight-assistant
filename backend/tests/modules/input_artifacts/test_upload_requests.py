from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from app.modules.organizations.access import CurrentCompanyContext
from app.db.session import set_tenant_scope
from app.modules.organizations.models import Company, CompanyMember
from app.modules.conversations.models import Conversation
from app.modules.input_artifacts.models import InputArtifactUploadRequest, InputArtifactVersion
from app.modules.identity.models import User
from app.modules.input_artifacts.upload_requests import (
    UploadRequestFingerprintConflictError,
    UploadRequestFencedError,
    complete_input_artifact_upload_request,
    finish_upload_request_with_error,
    reserve_input_artifact_upload_request,
)
from app.modules.input_artifacts.versions import create_received_input_artifact_version


_REQUEST_FINGERPRINT = "a" * 64


def _create_context_and_conversation(
    db: Session,
    user: User,
) -> tuple[CurrentCompanyContext, Conversation]:
    company = Company(name="input-artifact-upload-request-company")
    db.add(company)
    db.flush()
    membership = CompanyMember(
        company_id=company.id,
        user_id=user.id,
        role="analyst",
        status="approved",
    )
    conversation = Conversation(
        user_id=user.id,
        company_id=company.id,
        title="Upload test conversation",
    )
    db.add_all((membership, conversation))
    db.flush()
    set_tenant_scope(db, company.id)
    return CurrentCompanyContext(user=user, company=company, membership=membership), conversation


def test_reserve_upload_request_creates_first_generation(
    db_session: Session,
    test_user: User,
) -> None:
    context, conversation = _create_context_and_conversation(db_session, test_user)

    reservation = reserve_input_artifact_upload_request(
        db_session,
        context=context,
        conversation_id=conversation.id,
        idempotency_key="upload-1",
        trace_request_id="trace-1",
        lease_duration=timedelta(minutes=5),
        request_fingerprint=_REQUEST_FINGERPRINT,
    )

    assert reservation is not None
    assert reservation.disposition == "reserved"
    assert reservation.request.status == "receiving"
    assert reservation.request.attempt_generation == 1
    assert reservation.request.request_fingerprint == _REQUEST_FINGERPRINT
    assert reservation.request.lease_expires_at > datetime.now(timezone.utc)


def test_reserve_upload_request_returns_in_progress_for_active_lease(
    db_session: Session,
    test_user: User,
) -> None:
    context, conversation = _create_context_and_conversation(db_session, test_user)
    first = reserve_input_artifact_upload_request(
        db_session,
        context=context,
        conversation_id=conversation.id,
        idempotency_key="upload-1",
        trace_request_id="trace-1",
        lease_duration=timedelta(minutes=5),
        request_fingerprint=_REQUEST_FINGERPRINT,
    )

    second = reserve_input_artifact_upload_request(
        db_session,
        context=context,
        conversation_id=conversation.id,
        idempotency_key="upload-1",
        trace_request_id="trace-2",
        lease_duration=timedelta(minutes=5),
        request_fingerprint=_REQUEST_FINGERPRINT,
    )

    assert first is not None
    assert second is not None
    assert second.disposition == "in_progress"
    assert second.request.id == first.request.id
    assert second.request.attempt_generation == 1


def test_reserve_rejects_reused_key_with_different_fingerprint(
    db_session: Session,
    test_user: User,
) -> None:
    context, conversation = _create_context_and_conversation(db_session, test_user)
    first = reserve_input_artifact_upload_request(
        db_session,
        context=context,
        conversation_id=conversation.id,
        idempotency_key="upload-1",
        trace_request_id="trace-1",
        lease_duration=timedelta(minutes=5),
        request_fingerprint=_REQUEST_FINGERPRINT,
    )
    assert first is not None

    with pytest.raises(UploadRequestFingerprintConflictError):
        reserve_input_artifact_upload_request(
            db_session,
            context=context,
            conversation_id=conversation.id,
            idempotency_key="upload-1",
            trace_request_id="trace-2",
            lease_duration=timedelta(minutes=5),
            request_fingerprint="b" * 64,
        )

    current = db_session.get(InputArtifactUploadRequest, first.request.id)
    assert current is not None
    assert current.status == "receiving"
    assert current.attempt_generation == 1
    assert current.request_fingerprint == _REQUEST_FINGERPRINT


def test_reserve_upload_request_reclaims_an_expired_lease(
    db_session: Session,
    test_user: User,
) -> None:
    context, conversation = _create_context_and_conversation(db_session, test_user)
    first = reserve_input_artifact_upload_request(
        db_session,
        context=context,
        conversation_id=conversation.id,
        idempotency_key="upload-1",
        trace_request_id="trace-1",
        lease_duration=timedelta(minutes=5),
        request_fingerprint=_REQUEST_FINGERPRINT,
    )
    assert first is not None
    first.request.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()

    reclaimed = reserve_input_artifact_upload_request(
        db_session,
        context=context,
        conversation_id=conversation.id,
        idempotency_key="upload-1",
        trace_request_id="trace-2",
        lease_duration=timedelta(minutes=5),
        request_fingerprint=_REQUEST_FINGERPRINT,
    )

    assert reclaimed is not None
    assert reclaimed.disposition == "reserved"
    assert reclaimed.request.id == first.request.id
    assert reclaimed.request.attempt_generation == 2
    assert reclaimed.request.trace_request_id == "trace-2"
    assert reclaimed.request.lease_expires_at > datetime.now(timezone.utc)


def test_complete_upload_request_marks_owned_generation_completed(
    db_session: Session,
    test_user: User,
) -> None:
    context, conversation = _create_context_and_conversation(db_session, test_user)
    reservation = reserve_input_artifact_upload_request(
        db_session,
        context=context,
        conversation_id=conversation.id,
        idempotency_key="upload-1",
        trace_request_id="trace-1",
        lease_duration=timedelta(minutes=5),
        request_fingerprint=_REQUEST_FINGERPRINT,
    )
    assert reservation is not None
    version = create_received_input_artifact_version(
        db_session,
        company_id=context.company.id,
        uploaded_by_user_id=test_user.id,
        kind="attachment",
        original_filename="report.pdf",
        raw_object_key="input-artifacts/quarantine/report-1",
        byte_size=12,
        sha256="a" * 64,
        commit=False,
    )

    completed = complete_input_artifact_upload_request(
        db_session,
        context=context,
        conversation_id=conversation.id,
        idempotency_key="upload-1",
        attempt_generation=reservation.request.attempt_generation,
        payload_hash="a" * 64,
        artifact_version_id=version.id,
    )

    assert completed is not None
    assert completed.status == "completed"
    assert completed.payload_hash == "a" * 64
    assert completed.artifact_version_id == version.id
    assert completed.lease_expires_at is None
    assert completed.finished_at is not None


def test_stale_upload_generation_cannot_complete_after_reclaim(
    db_session: Session,
    test_user: User,
) -> None:
    context, conversation = _create_context_and_conversation(db_session, test_user)
    first = reserve_input_artifact_upload_request(
        db_session,
        context=context,
        conversation_id=conversation.id,
        idempotency_key="upload-1",
        trace_request_id="trace-1",
        lease_duration=timedelta(minutes=5),
        request_fingerprint=_REQUEST_FINGERPRINT,
    )
    assert first is not None
    stale_generation = first.request.attempt_generation
    first.request.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()
    reclaimed = reserve_input_artifact_upload_request(
        db_session,
        context=context,
        conversation_id=conversation.id,
        idempotency_key="upload-1",
        trace_request_id="trace-2",
        lease_duration=timedelta(minutes=5),
        request_fingerprint=_REQUEST_FINGERPRINT,
    )
    assert reclaimed is not None
    version = create_received_input_artifact_version(
        db_session,
        company_id=context.company.id,
        uploaded_by_user_id=test_user.id,
        kind="attachment",
        original_filename="report.pdf",
        raw_object_key="input-artifacts/quarantine/report-stale",
        byte_size=12,
        sha256="b" * 64,
        commit=False,
    )

    with pytest.raises(UploadRequestFencedError):
        complete_input_artifact_upload_request(
            db_session,
            context=context,
            conversation_id=conversation.id,
            idempotency_key="upload-1",
            attempt_generation=stale_generation,
            payload_hash="b" * 64,
            artifact_version_id=version.id,
        )

    current = db_session.get(InputArtifactUploadRequest, reclaimed.request.id)
    assert current is not None
    assert current.status == "receiving"
    assert current.attempt_generation == 2
    assert db_session.get(InputArtifactVersion, version.id) is None


def test_finish_upload_request_rejects_an_owned_generation(
    db_session: Session,
    test_user: User,
) -> None:
    context, conversation = _create_context_and_conversation(db_session, test_user)
    reservation = reserve_input_artifact_upload_request(
        db_session,
        context=context,
        conversation_id=conversation.id,
        idempotency_key="upload-1",
        trace_request_id="trace-1",
        lease_duration=timedelta(minutes=5),
        request_fingerprint=_REQUEST_FINGERPRINT,
    )
    assert reservation is not None

    finished = finish_upload_request_with_error(
        db_session,
        context=context,
        conversation_id=conversation.id,
        idempotency_key="upload-1",
        attempt_generation=reservation.request.attempt_generation,
        status="rejected",
        error_code=" input_unsupported_type ",
    )

    assert finished is not None
    assert finished.status == "rejected"
    assert finished.error_code == "input_unsupported_type"
    assert finished.lease_expires_at is None
    assert finished.finished_at is not None
    assert finished.artifact_version_id is None


def test_stale_upload_generation_cannot_finish_with_error_after_reclaim(
    db_session: Session,
    test_user: User,
) -> None:
    context, conversation = _create_context_and_conversation(db_session, test_user)
    first = reserve_input_artifact_upload_request(
        db_session,
        context=context,
        conversation_id=conversation.id,
        idempotency_key="upload-1",
        trace_request_id="trace-1",
        lease_duration=timedelta(minutes=5),
        request_fingerprint=_REQUEST_FINGERPRINT,
    )
    assert first is not None
    stale_generation = first.request.attempt_generation
    first.request.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()
    reclaimed = reserve_input_artifact_upload_request(
        db_session,
        context=context,
        conversation_id=conversation.id,
        idempotency_key="upload-1",
        trace_request_id="trace-2",
        lease_duration=timedelta(minutes=5),
        request_fingerprint=_REQUEST_FINGERPRINT,
    )
    assert reclaimed is not None

    with pytest.raises(UploadRequestFencedError):
        finish_upload_request_with_error(
            db_session,
            context=context,
            conversation_id=conversation.id,
            idempotency_key="upload-1",
            attempt_generation=stale_generation,
            status="failed",
            error_code="upload_storage_failed",
        )

    current = db_session.get(InputArtifactUploadRequest, reclaimed.request.id)
    assert current is not None
    assert current.status == "receiving"
    assert current.attempt_generation == 2
