from app.modules.documents.models import Documents
from app.modules.documents.repository import (
    delete_document,
    get_document,
    get_document_by_id,
    save_document,
    update_document,
)
from sqlalchemy.orm import Session


def save_document_service(
    db: Session,
    uploaded_by_user_id: int,
    name: str,
    content: str,
    source: str,
    company_id: int | None = None,
    min_view_role: str = "any",
) -> Documents:
    return save_document(
        db=db,
        uploaded_by_user_id=uploaded_by_user_id,
        name=name,
        content=content,
        source=source,
        company_id=company_id,
        min_view_role=min_view_role,
    )


def get_document_service(db: Session, company_id: int, role: str) -> list[Documents]:
    return get_document(db, company_id=company_id, role=role)


def get_document_by_id_service(
    db: Session, document_id: int, company_id: int, role: str
):
    record = get_document_by_id(db, document_id, company_id=company_id, role=role)

    if record is None:
        return None

    return record


def delete_document_service(
    db: Session,
    document_id: int,
    company_id: int,
    role: str,
    actor_user_id: int,
):
    record = delete_document(
        db,
        document_id,
        company_id=company_id,
        role=role,
        actor_user_id=actor_user_id,
    )

    if record is None:
        return None
    return record


def update_document_service(
    db: Session,
    document_id: int,
    name: str,
    content: str,
    source: str,
    company_id: int,
    role: str,
    actor_user_id: int,
    min_view_role: str,
):
    record = update_document(
        db=db,
        document_id=document_id,
        name=name,
        content=content,
        source=source,
        company_id=company_id,
        role=role,
        actor_user_id=actor_user_id,
        min_view_role=min_view_role,
    )

    if record is None:
        return None

    return record
