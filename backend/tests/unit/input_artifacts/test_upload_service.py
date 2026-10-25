from io import BytesIO

import pytest
from app.core.exceptions import (
    EmptyInputArtifactError,
    InputArtifactTooLargeError,
    InvalidInputArtifactNameError,
    UnsupportedInputArtifactTypeError,
)
from app.core.settings import get_settings
from app.db.session import set_tenant_scope
from app.modules.conversations.models import Conversation
from app.modules.identity.models import User
from app.modules.input_artifacts.models import (
    InputArtifact,
    InputArtifactUploadRequest,
    InputArtifactVersion,
)
from app.modules.input_artifacts.upload import upload_service
from app.modules.input_artifacts.upload.upload_requests import (
    UploadRequestFencedError,
    UploadRequestFingerprintConflictError,
)
from app.modules.organizations.access import CurrentCompanyContext
from app.modules.organizations.models import Company, CompanyMember
from sqlalchemy.orm import Session


def _create_context_and_conversation(
    db: Session,
    user: User,
) -> tuple[CurrentCompanyContext, Conversation]:
    company = Company(name="input-artifact-upload-service-company")
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
        title="Upload service test conversation",
    )
    db.add_all((membership, conversation))
    db.flush()
    set_tenant_scope(db, company.id)
    return CurrentCompanyContext(
        user=user, company=company, membership=membership
    ), conversation


def _command(
    *,
    context: CurrentCompanyContext,
    conversation_id: int,
    payload: bytes,
    idempotency_key: str = "upload-1",
    filename: str | None = "sales.csv",
) -> upload_service.UploadAttachmentCommand:
    return upload_service.UploadAttachmentCommand(
        context=context,
        conversation_id=conversation_id,
        idempotency_key=idempotency_key,
        trace_request_id="trace-1",
        file_stream=BytesIO(payload),
        original_filename=filename,
        declared_mime_type="text/csv",
    )


def test_upload_service_receives_one_attachment_and_persists_its_version(
    db_session: Session,
    test_user: User,
    tmp_path,
) -> None:
    context, conversation = _create_context_and_conversation(db_session, test_user)
    settings = get_settings().model_copy(update={"storage_dir": tmp_path})
    payload = b"region,sales\neast,10\n"

    outcome = upload_service.process_conversation_attachment_upload(
        db_session,
        command=_command(
            context=context,
            conversation_id=conversation.id,
            payload=payload,
        ),
        settings=settings,
    )

    assert outcome is not None
    assert outcome.disposition == "created"
    assert outcome.request.status == "completed"
    assert outcome.request.artifact_version_id is not None
    version = db_session.get(InputArtifactVersion, outcome.request.artifact_version_id)
    assert version is not None
    assert version.status == "received"
    assert (settings.storage_dir / version.raw_object_key).read_bytes() == payload


def test_upload_service_does_not_read_an_inaccessible_conversation(
    db_session: Session,
    test_user: User,
    tmp_path,
    monkeypatch,
) -> None:
    context, _ = _create_context_and_conversation(db_session, test_user)
    settings = get_settings().model_copy(update={"storage_dir": tmp_path})

    def inspection_must_not_run(**kwargs):
        raise AssertionError("inaccessible conversations must not inspect files")

    monkeypatch.setattr(
        upload_service, "inspect_input_artifact_file", inspection_must_not_run
    )

    outcome = upload_service.process_conversation_attachment_upload(
        db_session,
        command=_command(
            context=context,
            conversation_id=999_999,
            payload=b"region,sales\neast,10\n",
        ),
        settings=settings,
    )

    assert outcome is None
    assert db_session.query(InputArtifactUploadRequest).count() == 0
    assert not settings.input_artifact_quarantine_dir.exists()


def test_upload_service_rejects_a_reused_key_for_other_file(
    db_session: Session,
    test_user: User,
    tmp_path,
) -> None:
    context, conversation = _create_context_and_conversation(db_session, test_user)
    settings = get_settings().model_copy(update={"storage_dir": tmp_path})

    first = upload_service.process_conversation_attachment_upload(
        db_session,
        command=_command(
            context=context,
            conversation_id=conversation.id,
            payload=b"region,sales\neast,10\n",
        ),
        settings=settings,
    )
    assert first is not None

    with pytest.raises(UploadRequestFingerprintConflictError):
        upload_service.process_conversation_attachment_upload(
            db_session,
            command=_command(
                context=context,
                conversation_id=conversation.id,
                payload=b"region,sales\neast,11\n",
            ),
            settings=settings,
        )

    assert db_session.query(InputArtifactUploadRequest).count() == 1
    assert db_session.query(InputArtifactVersion).count() == 1


@pytest.mark.parametrize(
    ("payload", "filename", "settings_update", "expected_exception"),
    [
        (b"", "empty.txt", {}, EmptyInputArtifactError),
        (b"data", None, {}, InvalidInputArtifactNameError),
        (b"data", "payload.exe", {}, UnsupportedInputArtifactTypeError),
        (
            b"x" * (1024 * 1024 + 1),
            "large.txt",
            {"input_artifact_document_max_size_mb": 1},
            InputArtifactTooLargeError,
        ),
    ],
    ids=["empty", "invalid-name", "unsupported-type", "too-large"],
)
def test_upload_service_rejects_invalid_input_before_creating_a_request(
    db_session: Session,
    test_user: User,
    tmp_path,
    payload: bytes,
    filename: str | None,
    settings_update: dict,
    expected_exception: type[Exception],
) -> None:
    context, conversation = _create_context_and_conversation(db_session, test_user)
    settings = get_settings().model_copy(
        update={"storage_dir": tmp_path, **settings_update}
    )

    with pytest.raises(expected_exception):
        upload_service.process_conversation_attachment_upload(
            db_session,
            command=_command(
                context=context,
                conversation_id=conversation.id,
                payload=payload,
                filename=filename,
            ),
            settings=settings,
        )

    assert db_session.query(InputArtifactUploadRequest).count() == 0
    assert not settings.input_artifact_quarantine_dir.exists()


def test_upload_service_marks_request_failed_and_cleans_up_after_completion_error(
    db_session: Session,
    test_user: User,
    tmp_path,
    monkeypatch,
) -> None:
    context, conversation = _create_context_and_conversation(db_session, test_user)
    settings = get_settings().model_copy(update={"storage_dir": tmp_path})

    def completion_outage(*args, **kwargs):
        raise RuntimeError("completion service unavailable")

    monkeypatch.setattr(
        upload_service,
        "complete_input_artifact_upload_request",
        completion_outage,
    )

    outcome = upload_service.process_conversation_attachment_upload(
        db_session,
        command=_command(
            context=context,
            conversation_id=conversation.id,
            payload=b"region,sales\neast,10\n",
        ),
        settings=settings,
    )

    assert outcome is not None
    assert outcome.request.status == "failed"
    assert outcome.request.error_code == "input_ingestion_failed"
    assert db_session.query(InputArtifact).count() == 0
    assert list(settings.input_artifact_quarantine_dir.iterdir()) == []


def test_upload_service_cleans_up_without_overwriting_a_fenced_request(
    db_session: Session,
    test_user: User,
    tmp_path,
    monkeypatch,
) -> None:
    context, conversation = _create_context_and_conversation(db_session, test_user)
    settings = get_settings().model_copy(update={"storage_dir": tmp_path})

    def fenced_completion(*args, **kwargs):
        raise UploadRequestFencedError("upload request lost its lease")

    monkeypatch.setattr(
        upload_service,
        "complete_input_artifact_upload_request",
        fenced_completion,
    )

    with pytest.raises(UploadRequestFencedError):
        upload_service.process_conversation_attachment_upload(
            db_session,
            command=_command(
                context=context,
                conversation_id=conversation.id,
                payload=b"region,sales\neast,10\n",
            ),
            settings=settings,
        )

    current = db_session.query(InputArtifactUploadRequest).one()
    assert current.status == "receiving"
    assert db_session.query(InputArtifact).count() == 0
    assert list(settings.input_artifact_quarantine_dir.iterdir()) == []
