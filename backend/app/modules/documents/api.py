"""Documents are always scoped by the authenticated user's only company."""

from typing import Any, cast

from app.core.exceptions import (
    DocumentTooLargeError,
    DuplicateDocumentError,
    EmptyDocumentError,
    InsufficientStorageError,
    InvalidDocumentNameError,
    UnsupportedDocumentTypeError,
)
from app.core.settings import get_settings
from app.db.session import get_db
from app.modules.documents.chunk_repository import get_chunks_by_document_id
from app.modules.documents.chunk_schemas import ChunkOut
from app.modules.documents.ingestion import upload_document_service
from app.modules.documents.schemas import DocumentCreate, DocumentOut, DocumentUpdate
from app.modules.documents.service import (
    delete_document_service,
    get_document_by_id_service,
    get_document_service,
    save_document_service,
    update_document_service,
)
from app.modules.documents.tasks import process_document_task
from app.modules.organizations.access import (
    CurrentCompanyContext,
    get_current_company_context,
    require_analysis_permission,
)
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

router = APIRouter()
upload_router = APIRouter()  # Frozen: not mounted by the production application.


@router.get("/documents", response_model=list[DocumentOut])
def list_documents(
    context: CurrentCompanyContext = Depends(get_current_company_context),
    db: Session = Depends(get_db),
):
    return get_document_service(db, company_id=context.company.id, role=context.role)


def _validate_requested_visibility(context: CurrentCompanyContext, role: str) -> None:
    allowed = {
        "owner": {"any", "admin", "owner"},
        "admin": {"any", "admin"},
        "analyst": {"any"},
    }.get(context.role, set())
    if role not in allowed:
        raise HTTPException(
            status_code=403, detail="document visibility role is not allowed"
        )


@router.post(
    "/documents",
    response_model=DocumentOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_document(
    request: DocumentCreate,
    context: CurrentCompanyContext = Depends(require_analysis_permission),
    db: Session = Depends(get_db),
):
    _validate_requested_visibility(context, request.min_view_role)
    record = save_document_service(
        db=db,
        uploaded_by_user_id=context.user.id,
        company_id=context.company.id,
        name=request.name,
        content=request.content,
        source=request.source,
        min_view_role=request.min_view_role,
    )
    cast(Any, process_document_task).delay(
        document_id=record.id,
        company_id=context.company.id,
    )
    return record


def _document_or_404(db: Session, context: CurrentCompanyContext, document_id: int):
    record = get_document_by_id_service(
        db, document_id, company_id=context.company.id, role=context.role
    )
    if record is None:
        raise HTTPException(status_code=404, detail="document not found")
    return record


@router.get("/documents/{document_id}", response_model=DocumentOut)
def get_document(
    document_id: int,
    context: CurrentCompanyContext = Depends(get_current_company_context),
    db: Session = Depends(get_db),
):
    return _document_or_404(db, context, document_id)


@router.delete("/documents/{document_id}", response_model=DocumentOut)
def delete_document(
    document_id: int,
    context: CurrentCompanyContext = Depends(get_current_company_context),
    db: Session = Depends(get_db),
):
    record = delete_document_service(
        db,
        document_id,
        company_id=context.company.id,
        role=context.role,
        actor_user_id=context.user.id,
    )
    if record is None:
        raise HTTPException(status_code=404, detail="document not found")
    return record


@router.put(
    "/documents/{document_id}",
    response_model=DocumentOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def update_document(
    document_id: int,
    request: DocumentUpdate,
    context: CurrentCompanyContext = Depends(get_current_company_context),
    db: Session = Depends(get_db),
):
    _validate_requested_visibility(context, request.min_view_role)
    try:
        record = update_document_service(
            db=db,
            document_id=document_id,
            company_id=context.company.id,
            role=context.role,
            actor_user_id=context.user.id,
            name=request.name,
            content=request.content,
            source=request.source,
            min_view_role=request.min_view_role,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="document not found")
    cast(Any, process_document_task).delay(
        document_id=record.id,
        company_id=context.company.id,
    )
    return record


@upload_router.post(
    "/documents/upload",
    response_model=DocumentOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_document(
    file: UploadFile = File(...),
    context: CurrentCompanyContext = Depends(require_analysis_permission),
    db: Session = Depends(get_db),
):
    try:
        record = upload_document_service(
            db=db,
            uploaded_by_user_id=context.user.id,
            company_id=context.company.id,
            file_stream=file.file,
            original_name=file.filename,
            settings=get_settings(),
        )
        cast(Any, process_document_task).delay(
            document_id=record.id,
            company_id=context.company.id,
        )
        return record
    except DuplicateDocumentError:
        raise HTTPException(status_code=409, detail="document already exists")
    except InsufficientStorageError:
        raise HTTPException(status_code=507, detail="storage capacity exhausted")
    except (
        EmptyDocumentError,
        UnsupportedDocumentTypeError,
        DocumentTooLargeError,
        InvalidDocumentNameError,
    ) as error:
        raise HTTPException(status_code=422, detail=str(error))


@router.get("/documents/{document_id}/chunks", response_model=list[ChunkOut])
def get_document_chunks(
    document_id: int,
    context: CurrentCompanyContext = Depends(get_current_company_context),
    db: Session = Depends(get_db),
):
    _document_or_404(db, context, document_id)
    return get_chunks_by_document_id(db, document_id)
