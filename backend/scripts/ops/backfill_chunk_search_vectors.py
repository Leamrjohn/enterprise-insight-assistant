"""Fill the keyword index for chunks ingested before it existed.

Only touches rows where search_vector is NULL, so it is safe to run again.

Run:
    python -m scripts.ops.backfill_chunk_search_vectors
"""

from __future__ import annotations

from app.db.session import SessionLocal, set_tenant_scope
from app.main import app  # noqa: F401 - registers every model for the mapper
from app.modules.documents.chunks import DocumentChunk
from app.modules.documents.search_tokens import search_vector_expression
from app.modules.organizations.models import Company
from sqlalchemy import select, update

BATCH_SIZE = 500


def backfill_company(db, company_id: int) -> int:
    """Commit in batches so a long run does not hold one large transaction."""
    filled = 0
    while True:
        set_tenant_scope(db, company_id)
        rows = db.execute(
            select(DocumentChunk.id, DocumentChunk.content)
            .where(
                DocumentChunk.company_id == company_id,
                DocumentChunk.search_vector.is_(None),
            )
            .order_by(DocumentChunk.id)
            .limit(BATCH_SIZE)
        ).all()
        if not rows:
            return filled
        for chunk_id, content in rows:
            db.execute(
                update(DocumentChunk)
                .where(DocumentChunk.id == chunk_id)
                .values(search_vector=search_vector_expression(content))
            )
        db.commit()
        filled += len(rows)


def main() -> None:
    with SessionLocal() as db:
        company_ids = db.execute(select(Company.id)).scalars().all()
        for company_id in company_ids:
            print(f"company {company_id}: {backfill_company(db, company_id)} chunks")


if __name__ == "__main__":
    main()
