"""Documents are always scoped by the authenticated user's only company."""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.company_auth import CurrentCompanyContext, get_current_company_context
from app.core.exceptions import (
    DuplicateDocumentError,
    EmptyDocumentError,
    InvalidDocumentNameError,
    UnsupportedDocumentTypeError,
    DocumentTooLargeError,
)
from app.core.settings import get_settings
from app.db.session import get_db
from app.repositories.chunk_repository import get_chunks_by_document_id
from app.schemas.chunk import ChunkOut
from app.schemas.document import DocumentCreate, DocumentOut, DocumentUpdate
from app.services.document_ingestion_service import upload_document_service
from app.services.document_service import (
    delete_document_service,
    get_document_by_id_service,
    get_document_service,
    save_document_service,
    update_document_service,
)
from app.tasks.document_tasks import process_document_task

router = APIRouter()


@router.get("/documents", response_model=list[DocumentOut])
def list_documents(
    context: CurrentCompanyContext = Depends(get_current_company_context),
    db: Session = Depends(get_db),
):
    return get_document_service(db, company_id=context.company.id, role=context.role)


@router.post("/documents", response_model=DocumentOut)
def create_document(
    request: DocumentCreate,
    context: CurrentCompanyContext = Depends(get_current_company_context),
    db: Session = Depends(get_db),
):
    return save_document_service(
        db=db,
        uploaded_by_user_id=context.user.id,
        company_id=context.company.id,
        name=request.name,
        content=request.content,
        source=request.source,
        min_view_role=request.min_view_role,
    )


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
        db, document_id, company_id=context.company.id, role=context.role
    )
    if record is None:
        raise HTTPException(status_code=404, detail="document not found")
    return record


@router.put("/documents/{document_id}", response_model=DocumentOut)
def update_document(
    document_id: int,
    request: DocumentUpdate,
    context: CurrentCompanyContext = Depends(get_current_company_context),
    db: Session = Depends(get_db),
):
    record = update_document_service(
        db=db,
        document_id=document_id,
        company_id=context.company.id,
        role=context.role,
        name=request.name,
        content=request.content,
        source=request.source,
        min_view_role=request.min_view_role,
    )
    if record is None:
        raise HTTPException(status_code=404, detail="document not found")
    return record


@router.post(
    "/documents/upload",
    response_model=DocumentOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_document(
    file: UploadFile = File(...),
    context: CurrentCompanyContext = Depends(get_current_company_context),
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
        process_document_task.delay(
            document_id=record.id,
            company_id=context.company.id,
        )
        return record
    except DuplicateDocumentError:
        raise HTTPException(status_code=409, detail="document already exists")
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
