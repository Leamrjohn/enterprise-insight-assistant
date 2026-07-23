import pytest
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.models.document_chunk import DocumentChunk
from app.models.documents import Documents
from app.models.user import User
from app.services.document_ingestion_service import process_document_chunks
import app.services.document_ingestion_service as document_ingestion_service


def _create_pending_document(db: Session, user: User, suffix: str) -> Documents:
    document = Documents(
        user_id=user.id,
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

    monkeypatch.setattr(document_ingestion_service, "chunk_file", lambda _: chunk_texts)
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
        lambda _: ["first chunk"],
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
