from sqlalchemy.orm import Session
from app.models.documents import Documents
from sqlalchemy import select


def allowed_min_view_roles(role: str) -> tuple[str, ...]:
    if role == "owner":
        return ("any", "admin", "owner")
    if role == "admin":
        return ("any", "admin")
    return ("any",)


def save_document(
    db: Session,
    uploaded_by_user_id: int,
    name: str,
    content: str,
    source: str,
    company_id: int | None = None,
    min_view_role: str = "any",
):
    record = Documents(
        uploaded_by_user_id=uploaded_by_user_id,
        company_id=company_id,
        name=name,
        content=content,
        source=source,
        min_view_role=min_view_role,
        status="pending",
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_document(
    db: Session,
    company_id: int,
    role: str,
):
    return (
        db.query(Documents)
        .filter(
            Documents.company_id == company_id,
            Documents.min_view_role.in_(allowed_min_view_roles(role)),
        )
        .order_by(Documents.id.desc())
        .all()
    )


def get_document_by_id(db: Session, document_id: int, company_id: int, role: str):
    return (
        db.query(Documents)
        .filter(
            Documents.id == document_id,
            Documents.company_id == company_id,
            Documents.min_view_role.in_(allowed_min_view_roles(role)),
        )
        .first()
    )


def get_document_for_mutation(
    db: Session,
    *,
    document_id: int,
    company_id: int,
    role: str,
    actor_user_id: int,
):
    record = get_document_by_id(db, document_id, company_id, role)
    if record is None:
        return None
    if role not in {"owner", "admin", "analyst"}:
        return None
    if role not in {"owner", "admin"} and record.uploaded_by_user_id != actor_user_id:
        return None
    return record


def delete_document(
    db: Session,
    document_id: int,
    company_id: int,
    role: str,
    actor_user_id: int,
):
    record = get_document_for_mutation(
        db,
        document_id=document_id,
        company_id=company_id,
        role=role,
        actor_user_id=actor_user_id,
    )
    if record is None:
        return None

    db.delete(record)
    db.commit()
    return record


def update_document(
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
    record = get_document_for_mutation(
        db,
        document_id=document_id,
        company_id=company_id,
        role=role,
        actor_user_id=actor_user_id,
    )

    if record is None:
        return None
    if record.file_path is not None:
        raise ValueError("uploaded document content cannot be edited")

    record.name = name
    record.content = content
    record.source = source
    record.min_view_role = min_view_role
    record.status = "pending"
    record.error_message = None

    db.commit()
    db.refresh(record)
    return record


def get_document_by_sha256(
    db: Session, sha256: str, company_id: int | None
) -> Documents | None:
    statement = select(Documents).where(
        Documents.sha256 == sha256, Documents.company_id == company_id
    )
    return db.scalar(statement)


def add_uploaded_document(
    db: Session,
    *,
    uploaded_by_user_id: int,
    company_id: int | None,
    name: str,
    file_path: str,
    file_type: str,
    file_size: int,
    sha256: str,
) -> Documents:
    record = Documents(
        uploaded_by_user_id=uploaded_by_user_id,
        company_id=company_id,
        name=name,
        content=None,
        source="upload",
        file_path=file_path,
        file_type=file_type,
        file_size=file_size,
        sha256=sha256,
        status="pending",
        error_message=None,
    )
    db.add(record)
    db.flush()
    return record
