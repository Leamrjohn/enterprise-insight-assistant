from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.company_auth import CurrentCompanyContext, get_current_company_context
from app.db.session import get_db
from app.services.label_service import (
    create_label_service,
    list_labels_service,
    get_label_by_id_service,
    update_label_service,
    delete_label_service,
)
from app.schemas.labels import LabelCreate, LabelUpdate, LabelOut
from app.core.exceptions import DuplicateLabelError


router = APIRouter()


@router.post(
    "/labels",
    response_model=LabelOut,
    status_code=201,
)
def create_label(
    request_model: LabelCreate,
    db: Session = Depends(get_db),
    context: CurrentCompanyContext = Depends(get_current_company_context),
):
    try:
        return create_label_service(
            db, context.user.id, request_model.name, request_model.color
        )
    except DuplicateLabelError:
        raise HTTPException(status_code=409, detail="label name already exists")


@router.get("/labels/{label_id}", response_model=LabelOut)
def get_label(
    label_id: int,
    db: Session = Depends(get_db),
    context: CurrentCompanyContext = Depends(get_current_company_context),
):
    record = get_label_by_id_service(db, label_id, context.user.id)
    if record is None:
        raise HTTPException(status_code=404, detail="this label not found")
    else:
        return record


@router.get("/labels", response_model=list[LabelOut])
def list_labels(
    db: Session = Depends(get_db),
    context: CurrentCompanyContext = Depends(get_current_company_context),
):
    return list_labels_service(
        db=db,
        user_id=context.user.id,
    )


@router.patch("/labels/{label_id}", response_model=LabelOut)
def update_label(
    label_id: int,
    request_model: LabelUpdate,
    db: Session = Depends(get_db),
    context: CurrentCompanyContext = Depends(get_current_company_context),
):
    updates = request_model.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(
            status_code=422,
            detail="at least one field must have updates",
        )
    try:
        record = update_label_service(db, label_id, context.user.id, updates)
    except DuplicateLabelError:
        raise HTTPException(status_code=409, detail="label name already exists")
    if record is None:
        raise HTTPException(status_code=404, detail="this label not found")
    return record


@router.delete("/labels/{label_id}", status_code=204)
def delete_label(
    label_id: int,
    db: Session = Depends(get_db),
    context: CurrentCompanyContext = Depends(get_current_company_context),
):
    record = delete_label_service(db, label_id, context.user.id)
    if record is None:
        raise HTTPException(status_code=404, detail="this label not found")
