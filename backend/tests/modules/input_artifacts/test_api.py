from dataclasses import dataclass, field
from datetime import datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.db.session import set_tenant_scope
from app.modules.conversations.models import Conversation
from app.modules.identity.models import User
from app.modules.input_artifacts import api as input_artifacts_api
from app.modules.input_artifacts.api import _build_upload_response
from app.modules.input_artifacts.direct_upload_storage import (
    DirectUploadForm,
    DirectUploadObjectNotFoundError,
    DirectUploadStorageUnavailableError,
    StoredQuarantineObject,
)
from app.modules.input_artifacts.models import (
    ArtifactProcessingJob,
    InputArtifactUploadRequest,
    InputArtifactUploadSession,
    InputArtifactVersion,
)
from app.modules.input_artifacts.upload_requests import (
    complete_input_artifact_upload_request,
    reserve_input_artifact_upload_request,
)
from app.modules.input_artifacts.versions import create_received_input_artifact_version
from app.modules.organizations.access import CurrentCompanyContext
from app.modules.organizations.models import Company, CompanyMember


_REQUEST_FINGERPRINT = "a" * 64


@dataclass
class _FakeDirectUploadStorage:
    provider_name: str = "fake-object-storage"
    objects: dict[str, StoredQuarantineObject] = field(default_factory=dict)

    def create_quarantine_upload_form(
        self,
        *,
        object_key: str,
        byte_size: int,
        sha256_hex: str,
        expires_at: datetime,
    ) -> DirectUploadForm:
        return DirectUploadForm(
            url="https://object-storage.example.test/upload",
            fields={
                "key": object_key,
                "checksum": sha256_hex,
                "size": str(byte_size),
            },
            expires_at=expires_at,
        )

    def inspect_quarantine_object(
        self,
        *,
        object_key: str,
    ) -> StoredQuarantineObject:
        try:
            return self.objects[object_key]
        except KeyError as exc:
            raise DirectUploadObjectNotFoundError("fake object was not found") from exc


def _create_context_and_conversation(
    db: Session,
    user: User,
) -> tuple[CurrentCompanyContext, Conversation]:
    company = Company(name="input-artifact-api-company")
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
        title="Input artifact API test conversation",
    )
    db.add_all((membership, conversation))
    db.flush()
    set_tenant_scope(db, company.id)
    return CurrentCompanyContext(user=user, company=company, membership=membership), conversation


def _reserve_request(
    db: Session,
    *,
    context: CurrentCompanyContext,
    conversation: Conversation,
):
    reservation = reserve_input_artifact_upload_request(
        db,
        context=context,
        conversation_id=conversation.id,
        idempotency_key="upload-1",
        trace_request_id="trace-1",
        lease_duration=timedelta(minutes=5),
        request_fingerprint=_REQUEST_FINGERPRINT,
    )
    assert reservation is not None
    return reservation


def test_build_upload_response_includes_the_persisted_version_status(
    db_session: Session,
    test_user: User,
) -> None:
    context, conversation = _create_context_and_conversation(db_session, test_user)
    reservation = _reserve_request(
        db_session,
        context=context,
        conversation=conversation,
    )
    version = create_received_input_artifact_version(
        db_session,
        company_id=context.company.id,
        uploaded_by_user_id=test_user.id,
        kind="attachment",
        original_filename="report.pdf",
        raw_object_key="input-artifacts/quarantine/report.pdf",
        byte_size=12,
        sha256="b" * 64,
        commit=False,
    )
    completed = complete_input_artifact_upload_request(
        db_session,
        context=context,
        conversation_id=conversation.id,
        idempotency_key="upload-1",
        attempt_generation=reservation.request.attempt_generation,
        payload_hash="b" * 64,
        artifact_version_id=version.id,
    )
    assert completed is not None

    response = _build_upload_response(
        db_session,
        context=context,
        upload_request=completed,
    )

    assert response.upload_request_id == completed.id
    assert response.upload_status == "completed"
    assert response.artifact_version is not None
    assert response.artifact_version.version_id == version.id
    assert response.artifact_version.status == "received"
    assert response.error_code is None


def test_build_upload_response_has_no_version_while_receiving(
    db_session: Session,
    test_user: User,
) -> None:
    context, conversation = _create_context_and_conversation(db_session, test_user)
    reservation = _reserve_request(
        db_session,
        context=context,
        conversation=conversation,
    )

    response = _build_upload_response(
        db_session,
        context=context,
        upload_request=reservation.request,
    )

    assert response.upload_status == "receiving"
    assert response.artifact_version is None
    assert response.error_code is None


def test_build_upload_response_rejects_a_request_from_another_company(
    db_session: Session,
    test_user: User,
) -> None:
    context, conversation = _create_context_and_conversation(db_session, test_user)
    reservation = _reserve_request(
        db_session,
        context=context,
        conversation=conversation,
    )
    reservation.request.company_id = context.company.id + 1

    with pytest.raises(PermissionError):
        _build_upload_response(
            db_session,
            context=context,
            upload_request=reservation.request,
        )


def test_build_upload_response_rejects_a_missing_version(
    db_session: Session,
    test_user: User,
) -> None:
    context, conversation = _create_context_and_conversation(db_session, test_user)
    reservation = _reserve_request(
        db_session,
        context=context,
        conversation=conversation,
    )
    reservation.request.artifact_version_id = 999_999

    with db_session.no_autoflush:
        with pytest.raises(RuntimeError, match="no readable artifact version"):
            _build_upload_response(
                db_session,
                context=context,
                upload_request=reservation.request,
            )


def test_upload_attachment_creates_one_completed_version(
    client,
    db_session: Session,
    test_user: User,
    tmp_path,
    monkeypatch,
) -> None:
    context, conversation = _create_context_and_conversation(db_session, test_user)
    settings = get_settings().model_copy(update={"storage_dir": tmp_path})
    monkeypatch.setattr(input_artifacts_api, "get_settings", lambda: settings)

    response = client.post(
        f"/conversations/{conversation.id}/attachments",
        headers={"Idempotency-Key": "attachment-upload-1"},
        files={"file": ("notes.txt", b"quarterly notes", "text/plain")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["upload_status"] == "completed"
    assert body["attempt_generation"] == 1
    assert body["artifact_version"]["status"] == "received"
    assert body["error_code"] is None
    assert db_session.query(InputArtifactUploadRequest).count() == 1
    assert db_session.query(InputArtifactVersion).count() == 1
    assert len(list(settings.input_artifact_quarantine_dir.iterdir())) == 1


def test_upload_attachment_replays_the_completed_response_for_same_file(
    client,
    db_session: Session,
    test_user: User,
    tmp_path,
    monkeypatch,
) -> None:
    _, conversation = _create_context_and_conversation(db_session, test_user)
    settings = get_settings().model_copy(update={"storage_dir": tmp_path})
    monkeypatch.setattr(input_artifacts_api, "get_settings", lambda: settings)
    request = {
        "headers": {"Idempotency-Key": "attachment-upload-1"},
        "files": {"file": ("notes.txt", b"quarterly notes", "text/plain")},
    }

    first = client.post(f"/conversations/{conversation.id}/attachments", **request)
    second = client.post(f"/conversations/{conversation.id}/attachments", **request)

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json() == first.json()
    assert db_session.query(InputArtifactUploadRequest).count() == 1
    assert db_session.query(InputArtifactVersion).count() == 1


def test_upload_attachment_rejects_an_idempotency_key_reused_for_other_content(
    client,
    db_session: Session,
    test_user: User,
    tmp_path,
    monkeypatch,
) -> None:
    _, conversation = _create_context_and_conversation(db_session, test_user)
    settings = get_settings().model_copy(update={"storage_dir": tmp_path})
    monkeypatch.setattr(input_artifacts_api, "get_settings", lambda: settings)

    first = client.post(
        f"/conversations/{conversation.id}/attachments",
        headers={"Idempotency-Key": "attachment-upload-1"},
        files={"file": ("notes.txt", b"quarterly notes", "text/plain")},
    )
    conflict = client.post(
        f"/conversations/{conversation.id}/attachments",
        headers={"Idempotency-Key": "attachment-upload-1"},
        files={"file": ("notes.txt", b"changed notes", "text/plain")},
    )

    assert first.status_code == 201
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "idempotency_key_conflict"
    assert db_session.query(InputArtifactUploadRequest).count() == 1
    assert db_session.query(InputArtifactVersion).count() == 1


def test_initiate_attachment_upload_session_returns_direct_upload_form(
    client,
    db_session: Session,
    test_user: User,
    monkeypatch,
) -> None:
    _, conversation = _create_context_and_conversation(db_session, test_user)
    storage = _FakeDirectUploadStorage()
    monkeypatch.setattr(
        input_artifacts_api,
        "get_direct_upload_storage",
        lambda _settings: storage,
    )

    response = client.post(
        f"/conversations/{conversation.id}/attachment-upload-sessions",
        headers={"Idempotency-Key": "direct-upload-1"},
        json={
            "filename": "sales.csv",
            "byte_size": 1024,
            "mime_type": "text/csv",
            "sha256": "a" * 64,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["upload_status"] == "awaiting_upload"
    assert body["upload"]["method"] == "POST"
    assert body["upload"]["fields"]["checksum"] == "a" * 64
    session = db_session.query(InputArtifactUploadSession).one()
    assert body["upload_session_id"] == session.public_id
    assert body["upload"]["fields"]["key"] == session.staging_object_key


def test_initiate_attachment_upload_session_never_falls_back_to_local_disk(
    client,
    db_session: Session,
    test_user: User,
    monkeypatch,
) -> None:
    _, conversation = _create_context_and_conversation(db_session, test_user)

    def unavailable_storage(_settings):
        raise DirectUploadStorageUnavailableError("test storage is unavailable")

    monkeypatch.setattr(
        input_artifacts_api,
        "get_direct_upload_storage",
        unavailable_storage,
    )

    response = client.post(
        f"/conversations/{conversation.id}/attachment-upload-sessions",
        headers={"Idempotency-Key": "direct-upload-1"},
        json={
            "filename": "sales.csv",
            "byte_size": 1024,
            "mime_type": "text/csv",
            "sha256": "a" * 64,
        },
    )

    assert response.status_code == 503
    assert response.json()["code"] == "direct_upload_unavailable"
    assert db_session.query(InputArtifactUploadSession).count() == 0


def test_complete_attachment_upload_session_persists_verified_version_and_scan_job(
    client,
    db_session: Session,
    test_user: User,
    monkeypatch,
) -> None:
    _, conversation = _create_context_and_conversation(db_session, test_user)
    storage = _FakeDirectUploadStorage()
    monkeypatch.setattr(
        input_artifacts_api,
        "get_direct_upload_storage",
        lambda _settings: storage,
    )
    initiated = client.post(
        f"/conversations/{conversation.id}/attachment-upload-sessions",
        headers={"Idempotency-Key": "direct-upload-complete-1"},
        json={
            "filename": "sales.csv",
            "byte_size": 1024,
            "mime_type": "text/csv",
            "sha256": "a" * 64,
        },
    )
    assert initiated.status_code == 201
    session = db_session.query(InputArtifactUploadSession).one()
    storage.objects[session.staging_object_key] = StoredQuarantineObject(
        byte_size=1024,
        sha256_hex="a" * 64,
    )

    completed = client.post(
        f"/conversations/{conversation.id}/attachment-upload-sessions/"
        f"{session.public_id}/complete"
    )

    assert completed.status_code == 201
    body = completed.json()
    assert body["upload_status"] == "completed"
    assert body["artifact_version"]["status"] == "received"
    assert db_session.query(ArtifactProcessingJob).count() == 1
