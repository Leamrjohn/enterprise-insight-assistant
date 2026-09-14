from sqlalchemy.orm import Session
from app.modules.documents.chunks import DocumentChunk


def add_chunk(
    db: Session,
    *,
    document_id: int,
    company_id: int,
    chunk_index: int,
    content: str,
    token_count: int,
    embedding: list[float],
    page_number: int | None = None,
    paragraph_start: int | None = None,
    paragraph_end: int | None = None,
) -> DocumentChunk:
    chunk = DocumentChunk(
        document_id=document_id,
        company_id=company_id,
        chunk_index=chunk_index,
        content=content,
        token_count=token_count,
        embedding=embedding,
        page_number=page_number,
        paragraph_start=paragraph_start,
        paragraph_end=paragraph_end,
    )
    db.add(chunk)
    db.flush()
    return chunk


def get_chunks_by_document_id(
    db: Session,
    document_id: int,
) -> list[DocumentChunk]:
    return (
        db.query(DocumentChunk)
        .filter(
            DocumentChunk.document_id == document_id,
        )
        .order_by(DocumentChunk.chunk_index)
        .all()
    )
