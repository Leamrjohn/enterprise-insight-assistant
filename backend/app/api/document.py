from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.document import DocumentCreate, DocumentOut, DocumentUpdate
from app.services.document_service import (
    get_document_by_id_service,
    get_document_service,
    save_document_service,
    delete_document_service,
    update_document_service,
)
from app.core.auth import get_current_user
from app.models.user import User

from app.services.document_ingestion_service import upload_document_service
from app.tasks.document_tasks import process_document_task
from app.core.settings import get_settings
from app.core.exceptions import (
    DuplicateDocumentError,
    EmptyDocumentError,
    UnsupportedDocumentTypeError,
    DocumentTooLargeError,
    InvalidDocumentNameError,
)
from app.repositories.chunk_repository import get_chunks_by_document_id
from app.schemas.chunk import ChunkOut

router = APIRouter()


@router.get("/documents", response_model=list[DocumentOut])
def get_document(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_document_service(db, user_id=current_user.id)


@router.post("/documents", response_model=DocumentOut)
def create_document(
    request_model: DocumentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return save_document_service(
        db=db,
        user_id=current_user.id,
        name=request_model.name,
        content=request_model.content,
        source=request_model.source,
    )


@router.get("/documents/{document_id}", response_model=DocumentOut)
def get_document_by_id(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record = get_document_by_id_service(db, document_id, user_id=current_user.id)
    if record is None:
        raise HTTPException(status_code=404, detail="document not found")
    return record


@router.delete("/documents/{document_id}", response_model=DocumentOut)
def delete_document_by_id(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record = delete_document_service(db, document_id, user_id=current_user.id)

    if record is None:
        raise HTTPException(status_code=404, detail="document not found")

    return record


@router.put("/documents/{document_id}", response_model=DocumentOut)
def update_document_by_id(
    document_id: int,
    request_model: DocumentUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record = update_document_service(
        db=db,
        document_id=document_id,
        user_id=current_user.id,
        name=request_model.name,
        content=request_model.content,
        source=request_model.source,
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    try:
        record = upload_document_service(
            db=db,
            user_id=current_user.id,
            file_stream=file.file,
            original_name=file.filename,
            settings=settings,
        )
        process_document_task.delay(document_id=record.id)
        return record

    except DuplicateDocumentError:
        raise HTTPException(status_code=409, detail="document already exists")
    except (
        EmptyDocumentError,
        UnsupportedDocumentTypeError,
        DocumentTooLargeError,
        InvalidDocumentNameError,
    ) as e:
        raise HTTPException(status_code=422, detail=str(e))

@router.get("/documents/{document_id}/chunks", response_model=list[ChunkOut])
def get_document_chunks(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record = get_document_by_id_service(db, document_id, user_id=current_user.id)
    if record is None:
        raise HTTPException(status_code=404, detail="document not found")
    return get_chunks_by_document_id(db, document_id)
