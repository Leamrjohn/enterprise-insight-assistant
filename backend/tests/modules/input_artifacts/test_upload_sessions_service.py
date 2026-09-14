from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.db.session import set_tenant_scope
from app.modules.conversations.models import Conversation
from app.modules.identity.models import User
from app.modules.input_artifacts.direct_upload_storage import DirectUploadForm
from app.modules.input_artifacts.direct_upload_storage import (
    DirectUploadObjectNotFoundError,
    StoredQuarantineObject,
)
from app.modules.input_artifacts.models import (
    ArtifactProcessingJob,
    ArtifactProcessingOutboxEvent,
    InputArtifactUploadSession,
    InputArtifactVersion,
)
from app.modules.input_artifacts.upload_sessions import (
    CompleteAttachmentUploadCommand,
    InitiateAttachmentUploadCommand,
    UploadSessionFingerprintConflictError,
    complete_conversation_attachment_upload,
    initiate_conversation_attachment_upload,
)
from app.modules.organizations.access import CurrentCompanyContext
from app.modules.organizations.models import Company, CompanyMember


@dataclass
class FakeDirectUploadStorage:
    provider_name: str = "fake-object-storage"
    calls: list[dict] | None = None
    objects: dict[str, StoredQuarantineObject] | None = None

    def __post_init__(self) -> None:
        if self.calls is None:
            self.calls = []
        if self.objects is None:
            self.objects = {}

    def create_quarantine_upload_form(
        self,
        *,
        object_key: str,
        byte_size: int,
        sha256_hex: str,
        expires_at: datetime,
    ) -> DirectUploadForm:
        assert self.calls is not None
        self.calls.append(
            {
                "object_key": object_key,
                "byte_size": byte_size,
                "sha256_hex": sha256_hex,
            }
        )
        return DirectUploadForm(
            url="https://object-storage.example.test/upload",
            fields={"key": object_key, "checksum": sha256_hex},
            expires_at=expires_at,
        )

    def inspect_quarantine_object(
        self,
        *,
        object_key: str,
    ) -> StoredQuarantineObject:
        assert self.objects is not None
        if object_key not in self.objects:
            raise DirectUploadObjectNotFoundError("fake object was not found")
        return self.objects[object_key]


def _context_and_conversation(
    db: Session,
    user: User,
) -> tuple[CurrentCompanyContext, Conversation]:
    company = Company(name="direct-upload-session-service-company")
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
        title="Direct upload session service test",
    )
    db.add_all((membership, conversation))
    db.flush()
    set_tenant_scope(db, company.id)
    return CurrentCompanyContext(user=user, company=company, membership=membership), conversation


def _command(
    context: CurrentCompanyContext,
    conversation_id: int,
    *,
    idempotency_key: str = "direct-upload-1",
    sha256: str = "a" * 64,
) -> InitiateAttachmentUploadCommand:
    return InitiateAttachmentUploadCommand(
        context=context,
        conversation_id=conversation_id,
        idempotency_key=idempotency_key,
        trace_request_id="trace-direct-upload-1",
        original_filename="sales.csv",
        client_reported_byte_size=1024,
        client_reported_mime_type="text/csv",
        client_reported_sha256=sha256,
    )


def _completion_command(
    context: CurrentCompanyContext,
    *,
    conversation_id: int,
    upload_session_public_id: str,
) -> CompleteAttachmentUploadCommand:
    return CompleteAttachmentUploadCommand(
        context=context,
        conversation_id=conversation_id,
        upload_session_public_id=upload_session_public_id,
        trace_request_id="trace-direct-upload-complete-1",
    )


def test_initiate_upload_session_persists_one_server_owned_object_key(
    db_session: Session,
    test_user: User,
) -> None:
    context, conversation = _context_and_conversation(db_session, test_user)
    storage = FakeDirectUploadStorage()

    outcome = initiate_conversation_attachment_upload(
        db_session,
        command=_command(context, conversation.id),
        settings=get_settings(),
        direct_upload_storage=storage,
    )

    assert outcome is not None
    assert outcome.disposition == "created"
    assert outcome.upload_form is not None
    assert outcome.session.status == "awaiting_upload"
    assert outcome.session.staging_object_key.endswith(
        f"/{outcome.session.public_id}/payload"
    )
    assert outcome.upload_form.fields["key"] == outcome.session.staging_object_key
    assert outcome.session.client_reported_sha256 == "a" * 64
    assert db_session.query(InputArtifactUploadSession).count() == 1


def test_initiate_upload_session_replays_the_same_object_target(
    db_session: Session,
    test_user: User,
) -> None:
    context, conversation = _context_and_conversation(db_session, test_user)
    storage = FakeDirectUploadStorage()

    first = initiate_conversation_attachment_upload(
        db_session,
        command=_command(context, conversation.id),
        settings=get_settings(),
        direct_upload_storage=storage,
    )
    replay = initiate_conversation_attachment_upload(
        db_session,
        command=_command(context, conversation.id),
        settings=get_settings(),
        direct_upload_storage=storage,
    )

    assert first is not None and replay is not None
    assert replay.disposition == "replayed"
    assert replay.session.public_id == first.session.public_id
    assert replay.upload_form is not None and first.upload_form is not None
    assert replay.upload_form.fields["key"] == first.upload_form.fields["key"]


def test_initiate_upload_session_rejects_idempotency_key_reused_for_other_content(
    db_session: Session,
    test_user: User,
) -> None:
    context, conversation = _context_and_conversation(db_session, test_user)
    storage = FakeDirectUploadStorage()
    first = initiate_conversation_attachment_upload(
        db_session,
        command=_command(context, conversation.id),
        settings=get_settings(),
        direct_upload_storage=storage,
    )
    assert first is not None

    with pytest.raises(UploadSessionFingerprintConflictError):
        initiate_conversation_attachment_upload(
            db_session,
            command=_command(context, conversation.id, sha256="b" * 64),
            settings=get_settings(),
            direct_upload_storage=storage,
        )


def test_initiate_upload_session_expires_a_stale_session_without_new_upload_form(
    db_session: Session,
    test_user: User,
) -> None:
    context, conversation = _context_and_conversation(db_session, test_user)
    storage = FakeDirectUploadStorage()
    first = initiate_conversation_attachment_upload(
        db_session,
        command=_command(context, conversation.id),
        settings=get_settings(),
        direct_upload_storage=storage,
    )
    assert first is not None
    first.session.upload_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()

    replay = initiate_conversation_attachment_upload(
        db_session,
        command=_command(context, conversation.id),
        settings=get_settings(),
        direct_upload_storage=storage,
    )

    assert replay is not None
    assert replay.disposition == "terminal"
    assert replay.upload_form is None
    assert replay.session.status == "expired"
    assert replay.session.failure_code == "upload_session_expired"


def test_complete_upload_session_creates_received_version_and_queued_scan_job(
    db_session: Session,
    test_user: User,
) -> None:
    context, conversation = _context_and_conversation(db_session, test_user)
    storage = FakeDirectUploadStorage()
    initiated = initiate_conversation_attachment_upload(
        db_session,
        command=_command(context, conversation.id),
        settings=get_settings(),
        direct_upload_storage=storage,
    )
    assert initiated is not None
    assert storage.objects is not None
    storage.objects[initiated.session.staging_object_key] = StoredQuarantineObject(
        byte_size=1024,
        sha256_hex="a" * 64,
    )

    completed = complete_conversation_attachment_upload(
        db_session,
        command=_completion_command(
            context,
            conversation_id=conversation.id,
            upload_session_public_id=initiated.session.public_id,
        ),
        direct_upload_storage=storage,
    )

    assert completed is not None
    assert completed.disposition == "completed"
    assert completed.session.status == "completed"
    assert completed.artifact_version_id is not None
    version = db_session.query(InputArtifactVersion).one()
    job = db_session.query(ArtifactProcessingJob).one()
    outbox_event = db_session.query(ArtifactProcessingOutboxEvent).one()
    assert version.id == completed.artifact_version_id
    assert version.status == "received"
    assert version.raw_object_key == initiated.session.staging_object_key
    assert job.artifact_version_id == version.id
    assert job.stage == "scan"
    assert job.status == "queued"
    assert outbox_event.company_id == context.company.id
    assert outbox_event.job_id == job.id
    assert outbox_event.status == "pending"
    assert outbox_event.event_type == "artifact_processing_job.created"

    replay = complete_conversation_attachment_upload(
        db_session,
        command=_completion_command(
            context,
            conversation_id=conversation.id,
            upload_session_public_id=initiated.session.public_id,
        ),
        direct_upload_storage=storage,
    )
    assert replay is not None
    assert replay.disposition == "replayed"
    assert db_session.query(InputArtifactVersion).count() == 1
    assert db_session.query(ArtifactProcessingJob).count() == 1
    assert db_session.query(ArtifactProcessingOutboxEvent).count() == 1


def test_complete_upload_session_fails_when_object_metadata_differs(
    db_session: Session,
    test_user: User,
) -> None:
    context, conversation = _context_and_conversation(db_session, test_user)
    storage = FakeDirectUploadStorage()
    initiated = initiate_conversation_attachment_upload(
        db_session,
        command=_command(context, conversation.id),
        settings=get_settings(),
        direct_upload_storage=storage,
    )
    assert initiated is not None
    assert storage.objects is not None
    storage.objects[initiated.session.staging_object_key] = StoredQuarantineObject(
        byte_size=512,
        sha256_hex="b" * 64,
    )

    outcome = complete_conversation_attachment_upload(
        db_session,
        command=_completion_command(
            context,
            conversation_id=conversation.id,
            upload_session_public_id=initiated.session.public_id,
        ),
        direct_upload_storage=storage,
    )

    assert outcome is not None
    assert outcome.disposition == "terminal"
    assert outcome.session.status == "failed"
    assert outcome.session.failure_code == "uploaded_object_metadata_mismatch"
    assert db_session.query(InputArtifactVersion).count() == 0
    assert db_session.query(ArtifactProcessingJob).count() == 0
