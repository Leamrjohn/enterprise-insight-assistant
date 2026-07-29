from app.models.document_chunk import DocumentChunk
from app.repositories.chunk_repository import add_chunk
from app.utils.document_chunk import ChunkText, chunk_file, chunk_text_with_metadata
from typing import BinaryIO
from sqlalchemy.orm import Session
from app.core.settings import Settings
from app.models.documents import Documents
from app.repositories.document_repository import (
    add_uploaded_document,
    get_document_by_sha256,
)
from app.services.file_storage_service import save_document_file
from sqlalchemy.exc import IntegrityError
from app.core.rag.embeddings_local import LocalEmbeddingProvider
from app.core.exceptions import DuplicateDocumentError, EmptyDocumentError


def upload_document_service(
    db: Session,
    *,
    uploaded_by_user_id: int,
    company_id: int | None,
    file_stream: BinaryIO,
    original_name: str | None,
    settings: Settings,
) -> Documents:
    stored_file = save_document_file(
        file_stream=file_stream, original_name=original_name, settings=settings
    )
    try:
        existing_document = get_document_by_sha256(
            db, stored_file.sha256, company_id=company_id
        )
        if existing_document is not None:
            raise DuplicateDocumentError(
                f"Document with SHA256 {stored_file.sha256} already exists."
            )

        record = add_uploaded_document(
            db=db,
            uploaded_by_user_id=uploaded_by_user_id,
            company_id=company_id,
            name=stored_file.original_name,
            file_path=stored_file.relative_path,
            sha256=stored_file.sha256,
            file_size=stored_file.size_bytes,
            file_type=stored_file.extension,
        )
        db.commit()
        db.refresh(record)
        return record
    except IntegrityError as exc:
        db.rollback()
        stored_file.absolute_path.unlink(missing_ok=True)
        raise DuplicateDocumentError(
            f"Document with SHA256 {stored_file.sha256} already exists."
        ) from exc
    except Exception:
        db.rollback()
        stored_file.absolute_path.unlink(missing_ok=True)
        raise


def process_document_chunks(
    db: Session,
    document: Documents,
    settings: Settings,
) -> Documents:

    document_id = document.id
    if document.company_id is None:
        raise ValueError("Document company scope is missing")

    document.status = "processing"
    document.error_message = None
    db.commit()
    try:
        if document.file_path is not None:
            absolute_path = settings.storage_dir / document.file_path
            chunk_records = chunk_file(absolute_path, include_metadata=True)
        elif document.content:
            chunk_records = chunk_text_with_metadata(document.content)
        else:
            raise ValueError("Document has neither a file nor text content")
        if not chunk_records:
            raise EmptyDocumentError("Document has no extractable text")
        chunk_records = [
            record
            if isinstance(record, ChunkText)
            else ChunkText(
                content=record, paragraph_start=index + 1, paragraph_end=index + 1
            )
            for index, record in enumerate(chunk_records)
        ]
        chunk_texts = [record.content for record in chunk_records]

        embeddings = LocalEmbeddingProvider().embed_batch(chunk_texts)

        if len(embeddings) != len(chunk_texts):
            raise RuntimeError("Embedding count does not match document chunk count")
        db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).delete(
            synchronize_session=False
        )
        for index, (chunk_record, embedding) in enumerate(
            zip(chunk_records, embeddings)
        ):
            add_chunk(
                db=db,
                document_id=document_id,
                company_id=document.company_id,
                chunk_index=index,
                content=chunk_record.content,
                token_count=len(chunk_record.content.split()),
                embedding=embedding,
                paragraph_start=chunk_record.paragraph_start,
                paragraph_end=chunk_record.paragraph_end,
            )
        document.status = "completed"
        document.content = "\n\n".join(chunk_texts)
        db.commit()
        db.refresh(document)
        return document
    except Exception as exc:
        db.rollback()

        failed_document = db.get(Documents, document_id)
        if failed_document is not None:
            failed_document.status = "failed"
            failed_document.error_message = str(exc)
            db.commit()

        raise
