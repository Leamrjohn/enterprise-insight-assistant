import pytest
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.db.session import set_tenant_scope
from app.modules.organizations.models import Company, CompanyMember
from app.modules.documents.chunks import DocumentChunk
from app.modules.documents.models import Documents
from app.modules.identity.models import User
from app.modules.documents.ingestion import process_document_chunks
import app.modules.documents.ingestion as document_ingestion_service


def _create_pending_document(db: Session, user: User, suffix: str) -> Documents:
    company = Company(name=f"ingestion-company-{suffix}")
    db.add(company)
    db.flush()
    db.add(
        CompanyMember(
            user_id=user.id,
            company_id=company.id,
            role="owner",
            status="approved",
        )
    )
    db.flush()
    set_tenant_scope(db, company.id)
    document = Documents(
        uploaded_by_user_id=user.id,
        company_id=company.id,
        name=f"report-{suffix}.txt",
        content=None,
        source="upload",
        file_path=f"uploads/report-{suffix}.txt",
        file_type=".txt",
        file_size=20,
        sha256=f"sha-{suffix}",
        status="pending",
    )
    db.add(document)
    db.flush()
    return document


def test_process_document_chunks_saves_one_embedding_per_chunk(
    db_session: Session,
    test_user: User,
    monkeypatch,
) -> None:
    document = _create_pending_document(db_session, test_user, "success")
    chunk_texts = ["first chunk", "second chunk"]
    embeddings = [[0.1] * 384, [0.2] * 384]

    class FakeEmbeddingProvider:
        def embed_batch(self, texts: list[str]) -> list[list[float]]:
            assert texts == chunk_texts
            return embeddings

    monkeypatch.setattr(
        document_ingestion_service, "chunk_file", lambda _, **__: chunk_texts
    )
    monkeypatch.setattr(
        document_ingestion_service,
        "LocalEmbeddingProvider",
        FakeEmbeddingProvider,
    )

    result = process_document_chunks(
        db=db_session,
        document=document,
        settings=get_settings(),
    )

    chunks = (
        db_session.query(DocumentChunk)
        .filter(DocumentChunk.document_id == document.id)
        .order_by(DocumentChunk.chunk_index)
        .all()
    )

    assert result.status == "completed"
    assert result.content == "first chunk\n\nsecond chunk"
    assert [chunk.content for chunk in chunks] == chunk_texts
    assert [len(chunk.embedding) for chunk in chunks] == [384, 384]
    assert chunks[0].embedding[0] == pytest.approx(0.1)
    assert chunks[1].embedding[0] == pytest.approx(0.2)
    assert [(chunk.paragraph_start, chunk.paragraph_end) for chunk in chunks] == [
        (1, 1),
        (2, 2),
    ]


def test_process_document_chunks_marks_document_failed_when_embedding_fails(
    db_session: Session,
    test_user: User,
    monkeypatch,
) -> None:
    document = _create_pending_document(db_session, test_user, "failure")

    class FailingEmbeddingProvider:
        def embed_batch(self, texts: list[str]) -> list[list[float]]:
            raise RuntimeError("embedding service unavailable")

    monkeypatch.setattr(
        document_ingestion_service,
        "chunk_file",
        lambda _, **__: ["first chunk"],
    )
    monkeypatch.setattr(
        document_ingestion_service,
        "LocalEmbeddingProvider",
        FailingEmbeddingProvider,
    )

    with pytest.raises(RuntimeError, match="embedding service unavailable"):
        process_document_chunks(
            db=db_session,
            document=document,
            settings=get_settings(),
        )

    db_session.expire_all()
    stored_document = db_session.get(Documents, document.id)
    chunks = (
        db_session.query(DocumentChunk)
        .filter(DocumentChunk.document_id == document.id)
        .all()
    )

    assert stored_document is not None
    assert stored_document.status == "failed"
    assert stored_document.error_message == "embedding service unavailable"
    assert chunks == []


def test_process_manual_document_replaces_stale_chunks_atomically(
    db_session: Session,
    test_user: User,
    monkeypatch,
) -> None:
    company = Company(name="manual-ingestion-company")
    db_session.add(company)
    db_session.flush()
    db_session.add(
        CompanyMember(
            user_id=test_user.id,
            company_id=company.id,
            role="analyst",
            status="approved",
        )
    )
    db_session.flush()
    set_tenant_scope(db_session, company.id)
    document = Documents(
        uploaded_by_user_id=test_user.id,
        company_id=company.id,
        name="manual-note",
        content="new first paragraph\n\nnew second paragraph",
        source="manual",
        status="pending",
    )
    db_session.add(document)
    db_session.flush()
    db_session.add(
        DocumentChunk(
            document_id=document.id,
            company_id=company.id,
            chunk_index=0,
            content="stale content",
            token_count=2,
            embedding=[0.3] * 384,
        )
    )
    db_session.commit()

    class FakeEmbeddingProvider:
        def embed_batch(self, texts: list[str]) -> list[list[float]]:
            assert texts == ["new first paragraph\n\nnew second paragraph"]
            return [[0.4] * 384]

    monkeypatch.setattr(
        document_ingestion_service,
        "LocalEmbeddingProvider",
        FakeEmbeddingProvider,
    )

    result = process_document_chunks(
        db=db_session,
        document=document,
        settings=get_settings(),
    )
    chunks = (
        db_session.query(DocumentChunk)
        .filter(DocumentChunk.document_id == document.id)
        .order_by(DocumentChunk.chunk_index)
        .all()
    )

    assert result.status == "completed"
    assert [chunk.content for chunk in chunks] == [
        "new first paragraph\n\nnew second paragraph"
    ]
    assert chunks[0].embedding[0] == pytest.approx(0.4)
