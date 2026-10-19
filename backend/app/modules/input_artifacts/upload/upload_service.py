"""The complete synchronous receipt of one conversation attachment."""

from dataclasses import dataclass
from datetime import timedelta
from typing import BinaryIO, Literal

from sqlalchemy.orm import Session

from app.core.exceptions import (
    EmptyInputArtifactError,
    InputArtifactTooLargeError,
    InvalidInputArtifactNameError,
    UnsupportedInputArtifactTypeError,
)
from app.core.settings import Settings
from app.modules.conversations.service import get_conversation_service
from app.modules.input_artifacts.models import InputArtifactUploadRequest
from app.modules.input_artifacts.upload.request_fingerprint import (
    build_input_artifact_request_fingerprint,
)
from app.modules.input_artifacts.storage import (
    InspectedInputArtifactFile,
    StoredInputArtifactFile,
    discard_stored_input_artifact_file,
    inspect_input_artifact_file,
    store_input_artifact_file,
)
from app.modules.input_artifacts.upload.upload_requests import (
    UploadRequestFencedError,
    UploadRequestReservation,
    complete_input_artifact_upload_request,
    finish_upload_request_with_error,
    reserve_input_artifact_upload_request,
)
from app.modules.input_artifacts.versions import create_received_input_artifact_version
from app.modules.organizations.access import CurrentCompanyContext


_ATTACHMENT_KIND = "attachment"


class InputArtifactContentMismatchError(ValueError):
    """The stored bytes differ from the bytes inspected before reservation."""


@dataclass(frozen=True, slots=True)
class UploadAttachmentCommand:
    """All request-specific input for one attachment receipt."""

    context: CurrentCompanyContext
    conversation_id: int
    idempotency_key: str
    trace_request_id: str
    file_stream: BinaryIO
    original_filename: str | None
    declared_mime_type: str | None


@dataclass(frozen=True, slots=True)
class UploadAttachmentOutcome:
    """The only upload result exposed to the HTTP layer."""

    request: InputArtifactUploadRequest
    disposition: Literal["created", "in_progress", "terminal"]


def process_conversation_attachment_upload(
    db: Session,
    *,
    command: UploadAttachmentCommand,
    settings: Settings,
) -> UploadAttachmentOutcome | None:
    """Receive one attachment without exposing intermediate state to the route."""
    conversation = get_conversation_service(
        db,
        conversation_id=command.conversation_id,
        context=command.context,
    )
    if conversation is None:
        return None

    inspected_file = inspect_input_artifact_file(
        file_stream=command.file_stream,
        original_filename=command.original_filename,
        settings=settings,
    )
    fingerprint = build_input_artifact_request_fingerprint(
        company_id=command.context.company.id,
        submitted_by_user_id=command.context.user.id,
        conversation_id=conversation.id,
        kind=_ATTACHMENT_KIND,
        original_filename=inspected_file.original_filename,
        content_sha256=inspected_file.sha256,
    )
    reservation = reserve_input_artifact_upload_request(
        db,
        context=command.context,
        conversation_id=conversation.id,
        idempotency_key=command.idempotency_key,
        trace_request_id=command.trace_request_id,
        lease_duration=timedelta(
            seconds=settings.input_artifact_upload_lease_seconds
        ),
        request_fingerprint=fingerprint,
    )
    if reservation is None:
        return None
    if reservation.disposition != "reserved":
        return UploadAttachmentOutcome(
            request=reservation.request,
            disposition=reservation.disposition,
        )

    return _store_reserved_attachment(
        db,
        command=command,
        reservation=reservation,
        inspected_file=inspected_file,
        settings=settings,
    )


def _store_reserved_attachment(
    db: Session,
    *,
    command: UploadAttachmentCommand,
    reservation: UploadRequestReservation,
    inspected_file: InspectedInputArtifactFile,
    settings: Settings,
) -> UploadAttachmentOutcome:
    request = reservation.request
    stored_file: StoredInputArtifactFile | None = None
    try:
        stored_file = store_input_artifact_file(
            file_stream=command.file_stream,
            original_filename=command.original_filename,
            settings=settings,
        )
        if (
            stored_file.sha256 != inspected_file.sha256
            or stored_file.byte_size != inspected_file.byte_size
            or stored_file.original_filename != inspected_file.original_filename
            or stored_file.category != inspected_file.category
        ):
            raise InputArtifactContentMismatchError(
                "uploaded bytes changed after inspection"
            )

        version = create_received_input_artifact_version(
            db,
            company_id=command.context.company.id,
            uploaded_by_user_id=command.context.user.id,
            kind=_ATTACHMENT_KIND,
            original_filename=stored_file.original_filename,
            raw_object_key=stored_file.raw_object_key,
            byte_size=stored_file.byte_size,
            sha256=stored_file.sha256,
            declared_mime_type=command.declared_mime_type,
            commit=False,
        )
        completed = complete_input_artifact_upload_request(
            db,
            context=command.context,
            conversation_id=request.conversation_id,
            idempotency_key=request.idempotency_key,
            attempt_generation=request.attempt_generation,
            payload_hash=stored_file.sha256,
            artifact_version_id=version.id,
        )
        if completed is None:
            raise RuntimeError("upload request conversation is no longer available")
        return UploadAttachmentOutcome(request=completed, disposition="created")
    except InputArtifactContentMismatchError:
        db.rollback()
        _discard_if_stored(stored_file, settings=settings)
        return _failed_outcome(
            db,
            command=command,
            request=request,
            status="failed",
            error_code="input_content_mismatch",
        )
    except (
        EmptyInputArtifactError,
        InvalidInputArtifactNameError,
        UnsupportedInputArtifactTypeError,
        InputArtifactTooLargeError,
    ) as exc:
        return _failed_outcome(
            db,
            command=command,
            request=request,
            status="rejected",
            error_code={
                EmptyInputArtifactError: "input_empty",
                InvalidInputArtifactNameError: "input_invalid_name",
                UnsupportedInputArtifactTypeError: "input_unsupported_type",
                InputArtifactTooLargeError: "input_too_large",
            }[type(exc)],
        )
    except UploadRequestFencedError:
        db.rollback()
        _discard_if_stored(stored_file, settings=settings)
        raise
    except Exception:
        db.rollback()
        _discard_if_stored(stored_file, settings=settings)
        return _failed_outcome(
            db,
            command=command,
            request=request,
            status="failed",
            error_code="input_ingestion_failed",
        )


def _discard_if_stored(
    stored_file: StoredInputArtifactFile | None,
    *,
    settings: Settings,
) -> None:
    if stored_file is not None:
        discard_stored_input_artifact_file(stored_file, settings=settings)


def _failed_outcome(
    db: Session,
    *,
    command: UploadAttachmentCommand,
    request: InputArtifactUploadRequest,
    status: Literal["rejected", "failed"],
    error_code: str,
) -> UploadAttachmentOutcome:
    finished = finish_upload_request_with_error(
        db,
        context=command.context,
        conversation_id=request.conversation_id,
        idempotency_key=request.idempotency_key,
        attempt_generation=request.attempt_generation,
        status=status,
        error_code=error_code,
    )
    if finished is None:
        raise RuntimeError("upload request conversation is no longer available")
    return UploadAttachmentOutcome(request=finished, disposition="created")
