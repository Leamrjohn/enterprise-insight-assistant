from typing import Annotated

from fastapi import APIRouter, Depends, File, Header, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.exceptions import (
    EmptyInputArtifactError,
    InputArtifactTooLargeError,
    InvalidInputArtifactNameError,
    UnsupportedInputArtifactTypeError,
)
from app.core.settings import get_settings
from app.db.session import get_db
from app.modules.input_artifacts.upload.direct_upload_storage import (
    DirectUploadStorageUnavailableError,
    get_direct_upload_storage,
)
from app.modules.input_artifacts.models import InputArtifactUploadRequest, InputArtifactUploadSession
from app.modules.input_artifacts.repository import (
    get_input_artifact_version_for_company,
)
from app.modules.input_artifacts.schemas import (
    AttachmentUploadSessionInitiate,
    AttachmentUploadSessionOut,
    DirectUploadFormOut,
    InputArtifactUploadOut,
    InputArtifactVersionReceiptOut,
)
from app.modules.input_artifacts.upload.upload_service import (
    UploadAttachmentCommand,
    process_conversation_attachment_upload,
)
from app.modules.input_artifacts.upload.upload_sessions import (
    CompleteAttachmentUploadCommand,
    InitiateAttachmentUploadCommand,
    UploadSessionCompletionOutcome,
    UploadSessionFingerprintConflictError,
    UploadSessionInitiationOutcome,
    complete_conversation_attachment_upload,
    initiate_conversation_attachment_upload,
)
from app.modules.input_artifacts.upload.upload_requests import (
    UploadRequestFencedError,
    UploadRequestFingerprintConflictError,
)
from app.modules.organizations.access import (
    CurrentCompanyContext,
    require_analysis_permission,
)


router = APIRouter()

_INPUT_ERROR_CODES = {
    EmptyInputArtifactError: "input_empty",
    InvalidInputArtifactNameError: "input_invalid_name",
    UnsupportedInputArtifactTypeError: "input_unsupported_type",
    InputArtifactTooLargeError: "input_too_large",
}


def _error_response(
    *,
    status_code: int,
    code: str,
    message: str,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"code": code, "message": message, "details": []},
    )


def _build_upload_response(
    db: Session,
    *,
    context: CurrentCompanyContext,
    upload_request: InputArtifactUploadRequest,
) -> InputArtifactUploadOut:
    if upload_request.company_id != context.company.id:
        raise PermissionError(
            "upload request is not available in the current company"
        )

    artifact_version = None
    if upload_request.artifact_version_id is not None:
        version = get_input_artifact_version_for_company(
            db,
            version_id=upload_request.artifact_version_id,
            company_id=context.company.id,
        )
        if version is None:
            raise RuntimeError(
                "completed upload request has no readable artifact version"
            )

        artifact_version = InputArtifactVersionReceiptOut(
            version_id=version.id,
            status=version.status,
        )

    return InputArtifactUploadOut(
        upload_request_id=upload_request.id,
        upload_status=upload_request.status,
        attempt_generation=upload_request.attempt_generation,
        artifact_version=artifact_version,
        error_code=upload_request.error_code,
    )


def _build_upload_session_response(
    outcome: UploadSessionInitiationOutcome,
) -> AttachmentUploadSessionOut:
    session: InputArtifactUploadSession = outcome.session
    upload = (
        DirectUploadFormOut(
            url=outcome.upload_form.url,
            fields=outcome.upload_form.fields,
            expires_at=outcome.upload_form.expires_at,
        )
        if outcome.upload_form is not None
        else None
    )
    return AttachmentUploadSessionOut(
        upload_session_id=session.public_id,
        upload_status=session.status,
        upload=upload,
        error_code=session.failure_code,
    )


def _build_upload_session_completion_response(
    db: Session,
    *,
    context: CurrentCompanyContext,
    outcome: UploadSessionCompletionOutcome,
) -> AttachmentUploadSessionOut:
    artifact_version = None
    if outcome.artifact_version_id is not None:
        version = get_input_artifact_version_for_company(
            db,
            version_id=outcome.artifact_version_id,
            company_id=context.company.id,
        )
        if version is None:
            raise RuntimeError("completed upload session has no readable artifact version")
        artifact_version = InputArtifactVersionReceiptOut(
            version_id=version.id,
            status=version.status,
        )
    return AttachmentUploadSessionOut(
        upload_session_id=outcome.session.public_id,
        upload_status=outcome.session.status,
        artifact_version=artifact_version,
        error_code=outcome.session.failure_code,
    )


@router.post(
    "/conversations/{conversation_id}/attachment-upload-sessions",
    response_model=AttachmentUploadSessionOut,
    status_code=status.HTTP_201_CREATED,
)
def initiate_conversation_attachment_upload_session(
    conversation_id: int,
    request_model: AttachmentUploadSessionInitiate,
    request: Request,
    response: Response,
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=1, max_length=128),
    ] = "",
    context: CurrentCompanyContext = Depends(require_analysis_permission),
    db: Session = Depends(get_db),
) -> AttachmentUploadSessionOut | JSONResponse:
    try:
        outcome = initiate_conversation_attachment_upload(
            db,
            command=InitiateAttachmentUploadCommand(
                context=context,
                conversation_id=conversation_id,
                idempotency_key=idempotency_key,
                trace_request_id=request.state.request_id,
                original_filename=request_model.filename,
                client_reported_byte_size=request_model.byte_size,
                client_reported_mime_type=request_model.mime_type,
                client_reported_sha256=request_model.sha256,
            ),
            settings=get_settings(),
            direct_upload_storage=get_direct_upload_storage(get_settings()),
        )
    except DirectUploadStorageUnavailableError:
        return _error_response(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="direct_upload_unavailable",
            message="文件上传服务暂时不可用。",
        )
    except tuple(_INPUT_ERROR_CODES) as exc:
        return _error_response(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code=_INPUT_ERROR_CODES[type(exc)],
            message="上传文件不符合要求。",
        )
    except UploadSessionFingerprintConflictError:
        return _error_response(
            status_code=status.HTTP_409_CONFLICT,
            code="idempotency_key_conflict",
            message="幂等键已被不同上传内容使用。",
        )
    except ValueError:
        return _error_response(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code="invalid_upload_request",
            message="上传请求参数无效。",
        )
    if outcome is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    if outcome.disposition == "replayed":
        response.status_code = status.HTTP_200_OK
    elif outcome.disposition == "in_progress":
        response.status_code = status.HTTP_202_ACCEPTED
    elif outcome.disposition == "terminal" and outcome.session.status == "expired":
        return _error_response(
            status_code=status.HTTP_410_GONE,
            code="upload_session_expired",
            message="上传凭证已过期，请重新选择文件后上传。",
        )
    elif outcome.disposition == "terminal":
        response.status_code = status.HTTP_200_OK
    return _build_upload_session_response(outcome)


@router.post(
    "/conversations/{conversation_id}/attachment-upload-sessions/{upload_session_id}/complete",
    response_model=AttachmentUploadSessionOut,
    status_code=status.HTTP_201_CREATED,
)
def complete_conversation_attachment_upload_session(
    conversation_id: int,
    upload_session_id: str,
    request: Request,
    response: Response,
    context: CurrentCompanyContext = Depends(require_analysis_permission),
    db: Session = Depends(get_db),
) -> AttachmentUploadSessionOut | JSONResponse:
    try:
        outcome = complete_conversation_attachment_upload(
            db,
            command=CompleteAttachmentUploadCommand(
                context=context,
                conversation_id=conversation_id,
                upload_session_public_id=upload_session_id,
                trace_request_id=request.state.request_id,
            ),
            direct_upload_storage=get_direct_upload_storage(get_settings()),
        )
    except DirectUploadStorageUnavailableError:
        return _error_response(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="direct_upload_unavailable",
            message="文件上传服务暂时不可用。",
        )
    except ValueError:
        return _error_response(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code="invalid_upload_completion",
            message="上传完成确认参数无效。",
        )

    if outcome is None:
        raise HTTPException(status_code=404, detail="upload session not found")
    if outcome.disposition == "replayed":
        response.status_code = status.HTTP_200_OK
    elif outcome.disposition == "in_progress":
        response.status_code = status.HTTP_202_ACCEPTED
    elif outcome.session.status == "expired":
        return _error_response(
            status_code=status.HTTP_410_GONE,
            code="upload_session_expired",
            message="上传凭证已过期，请重新选择文件后上传。",
        )
    elif outcome.session.status in {"rejected", "failed"}:
        return _error_response(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code=outcome.session.failure_code or "upload_session_failed",
            message="文件上传未能通过服务器校验，请重新上传。",
        )
    return _build_upload_session_completion_response(
        db,
        context=context,
        outcome=outcome,
    )


@router.post(
    "/conversations/{conversation_id}/attachments",
    response_model=InputArtifactUploadOut,
)
def upload_conversation_attachment(
    conversation_id: int,
    request: Request,
    response: Response,
    file: UploadFile = File(...),
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=1, max_length=128),
    ] = "",
    context: CurrentCompanyContext = Depends(require_analysis_permission),
    db: Session = Depends(get_db),
) -> InputArtifactUploadOut | JSONResponse:
    settings = get_settings()
    command = UploadAttachmentCommand(
        context=context,
        conversation_id=conversation_id,
        idempotency_key=idempotency_key,
        trace_request_id=request.state.request_id,
        file_stream=file.file,
        original_filename=file.filename,
        declared_mime_type=file.content_type,
    )
    try:
        outcome = process_conversation_attachment_upload(
            db,
            command=command,
            settings=settings,
        )
    except tuple(_INPUT_ERROR_CODES) as exc:
        return _error_response(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code=_INPUT_ERROR_CODES[type(exc)],
            message="上传文件不符合要求。",
        )
    except UploadRequestFingerprintConflictError:
        return _error_response(
            status_code=status.HTTP_409_CONFLICT,
            code="idempotency_key_conflict",
            message="幂等键已被不同上传内容使用。",
        )
    except UploadRequestFencedError:
        return _error_response(
            status_code=status.HTTP_409_CONFLICT,
            code="upload_request_fenced",
            message="上传请求已失去处理权限，请使用相同幂等键重试。",
        )
    except ValueError:
        return _error_response(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code="invalid_upload_request",
            message="上传请求参数无效。",
        )

    if outcome is None:
        raise HTTPException(status_code=404, detail="conversation not found")

    if outcome.disposition == "in_progress":
        response.status_code = status.HTTP_202_ACCEPTED
        return _build_upload_response(
            db,
            context=context,
            upload_request=outcome.request,
        )
    if outcome.disposition == "terminal":
        return _build_upload_response(
            db,
            context=context,
            upload_request=outcome.request,
        )

    upload_request = outcome.request
    if upload_request.status == "completed":
        response.status_code = status.HTTP_201_CREATED
    elif upload_request.status == "rejected":
        response.status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    elif upload_request.status == "failed":
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    else:
        raise RuntimeError("reserved upload request did not reach a terminal state")

    return _build_upload_response(
        db,
        context=context,
        upload_request=upload_request,
    )
