from sqlalchemy.orm import Session

from app.repositories.document_repository import (
    get_document,
    save_document,
    get_document_by_id,
    delete_document,
    update_document,
)


def save_document_service(
    db: Session,
    uploaded_by_user_id: int,
    name: str,
    content: str,
    source: str,
    company_id: int | None = None,
    min_view_role: str = "any",
) -> dict:
    record = save_document(
        db=db,
        uploaded_by_user_id=uploaded_by_user_id,
        name=name,
        content=content,
        source=source,
        company_id=company_id,
        min_view_role=min_view_role,
    )
    return {
        "id": record.id,
        "company_id": record.company_id,
        "name": record.name,
        "content": record.content,
        "source": record.source,
    }


def get_document_service(db: Session, company_id: int, role: str) -> list[dict]:
    documents = get_document(db, company_id=company_id, role=role)
    result = []
    for document in documents:
        result.append(
            {
                "id": document.id,
                "company_id": document.company_id,
                "name": document.name,
                "content": document.content,
                "source": document.source,
                "min_view_role": document.min_view_role,
            }
        )
    return result


def get_document_by_id_service(
    db: Session, document_id: int, company_id: int, role: str
):
    record = get_document_by_id(db, document_id, company_id=company_id, role=role)

    if record is None:
        return None

    return {
        "id": record.id,
        "company_id": record.company_id,
        "name": record.name,
        "content": record.content,
        "source": record.source,
        "min_view_role": record.min_view_role,
    }


def delete_document_service(db: Session, document_id: int, company_id: int, role: str):
    record = delete_document(db, document_id, company_id=company_id, role=role)

    if record is None:
        return None
    return {
        "id": record.id,
        "company_id": record.company_id,
        "name": record.name,
        "content": record.content,
        "source": record.source,
        "min_view_role": record.min_view_role,
    }


def update_document_service(
    db: Session,
    document_id: int,
    name: str,
    content: str,
    source: str,
    company_id: int,
    role: str,
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
        min_view_role=min_view_role,
    )

    if record is None:
        return None

    return {
        "id": record.id,
        "company_id": record.company_id,
        "name": record.name,
        "content": record.content,
        "source": record.source,
        "min_view_role": record.min_view_role,
    }
