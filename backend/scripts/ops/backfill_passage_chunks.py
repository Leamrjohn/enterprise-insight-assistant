"""Add passage chunks to documents ingested before they existed.

Only adds rows, and skips documents that already have passages, so it is safe to
run again.  Other chunks stay as they are: published reports cite them by id.

Run:
    python -m scripts.ops.backfill_passage_chunks
"""

from __future__ import annotations

from app.db.session import SessionLocal, set_tenant_scope
from app.main import app  # noqa: F401 - registers every model for the mapper
from app.modules.documents.chunk_repository import add_chunk
from app.modules.documents.chunks import DocumentChunk
from app.modules.documents.ingestion import passage_records
from app.modules.documents.models import Documents
from app.modules.knowledge.rag.embeddings import EmbeddingProvider
from app.modules.knowledge.rag.embeddings_local import LocalEmbeddingProvider
from app.modules.organizations.models import Company
from app.utils.document_chunk import PASSAGE_CHUNK_STRATEGY, chunk_text_with_metadata
from sqlalchemy import select


def backfill_company(db, company_id: int, embedder: EmbeddingProvider) -> int:
    """Commit one document at a time; a rerun picks up where a failure stopped."""
    set_tenant_scope(db, company_id)
    has_passages = (
        select(DocumentChunk.id)
        .where(
            DocumentChunk.document_id == Documents.id,
            DocumentChunk.chunk_strategy == PASSAGE_CHUNK_STRATEGY,
        )
        .exists()
    )
    rows = db.execute(
        select(Documents.id, Documents.content)
        .where(
            Documents.company_id == company_id,
            Documents.status == "completed",
            Documents.content.is_not(None),
            ~has_passages,
        )
        .order_by(Documents.id)
    ).all()
    for document_id, content in rows:
        records = passage_records(content, chunk_text_with_metadata(content))
        embeddings = embedder.embed_batch([record.content for record in records])
        if len(embeddings) != len(records):
            raise RuntimeError("Embedding count does not match document chunk count")
        for index, (record, embedding) in enumerate(zip(records, embeddings)):
            add_chunk(
                db=db,
                document_id=document_id,
                company_id=company_id,
                chunk_strategy=PASSAGE_CHUNK_STRATEGY,
                chunk_index=index,
                content=record.content,
                token_count=len(record.content.split()),
                embedding=embedding,
                paragraph_start=record.paragraph_start,
                paragraph_end=record.paragraph_end,
            )
        db.commit()
        set_tenant_scope(db, company_id)
    return len(rows)


def main() -> None:
    embedder = LocalEmbeddingProvider()
    with SessionLocal() as db:
        company_ids = db.execute(select(Company.id)).scalars().all()
        total = sum(backfill_company(db, id_, embedder) for id_ in company_ids)
    print(f"backfilled {total} documents across {len(company_ids)} companies")


if __name__ == "__main__":
    main()
