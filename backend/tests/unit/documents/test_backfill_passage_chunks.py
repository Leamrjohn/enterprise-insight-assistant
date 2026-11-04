from app.db.session import set_tenant_scope
from app.modules.documents.chunks import DocumentChunk
from app.modules.documents.models import Documents
from app.modules.identity.models import User
from app.modules.organizations.models import Company, CompanyMember
from app.utils.document_chunk import PARAGRAPH_CHUNK_STRATEGY, PASSAGE_CHUNK_STRATEGY
from scripts.ops.backfill_passage_chunks import backfill_company
from sqlalchemy.orm import Session


class _FakeEmbedder:
    def __init__(self) -> None:
        self.texts: list[str] = []

    def embed(self, text: str) -> list[float]:
        return [0.1] * 384

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        self.texts.extend(texts)
        return [[0.1] * 384 for _ in texts]


def _company_with_old_document(db: Session, user: User, content: str) -> Documents:
    company = Company(name="backfill-company")
    db.add(company)
    db.flush()
    db.add(
        CompanyMember(
            user_id=user.id, company_id=company.id, role="owner", status="approved"
        )
    )
    db.flush()
    set_tenant_scope(db, company.id)
    document = Documents(
        uploaded_by_user_id=user.id,
        company_id=company.id,
        name="old.md",
        content=content,
        source="upload",
        file_type=".md",
        file_size=len(content),
        sha256="backfill-sha",
        status="completed",
    )
    db.add(document)
    db.flush()
    db.add(
        DocumentChunk(
            document_id=document.id,
            company_id=company.id,
            chunk_strategy=PARAGRAPH_CHUNK_STRATEGY,
            chunk_index=0,
            content=content,
            token_count=1,
            embedding=[0.2] * 384,
        )
    )
    db.commit()
    return document


def _chunks(db: Session, document: Documents) -> list[DocumentChunk]:
    set_tenant_scope(db, document.company_id)
    return (
        db.query(DocumentChunk)
        .filter(DocumentChunk.document_id == document.id)
        .order_by(DocumentChunk.chunk_strategy, DocumentChunk.chunk_index)
        .all()
    )


def test_backfill_adds_passages_and_leaves_existing_chunks_alone(
    db_session: Session, test_user: User
) -> None:
    document = _company_with_old_document(db_session, test_user, "# 甲\n\n正文")
    old_chunk_id = _chunks(db_session, document)[0].id

    filled = backfill_company(db_session, document.company_id, _FakeEmbedder())

    chunks = _chunks(db_session, document)
    assert filled == 1
    assert [chunk.chunk_strategy for chunk in chunks] == [
        PARAGRAPH_CHUNK_STRATEGY,
        PASSAGE_CHUNK_STRATEGY,
    ]
    assert chunks[0].id == old_chunk_id
    assert chunks[1].content == "甲\n正文"


def test_backfill_can_run_again_without_adding_anything(
    db_session: Session, test_user: User
) -> None:
    document = _company_with_old_document(db_session, test_user, "# 甲\n\n正文")
    backfill_company(db_session, document.company_id, _FakeEmbedder())
    second_embedder = _FakeEmbedder()

    filled = backfill_company(db_session, document.company_id, second_embedder)

    assert filled == 0
    assert second_embedder.texts == []
    assert len(_chunks(db_session, document)) == 2
