from uuid import uuid4

import pytest

from app.core.settings import get_settings
from app.core.rag.embeddings_local import LocalEmbeddingProvider
from app.core.rag.retrieval import retrieve_evidence
from app.db.session import SessionLocal
from app.models.document_chunk import DocumentChunk
from app.models.documents import Documents
from app.models.user import User
from app.tasks.document_tasks import process_document_task
import app.services.document_ingestion_service as document_ingestion_service
import app.tasks.document_tasks as document_tasks


def test_document_worker_persists_mocked_ingestion_output(monkeypatch) -> None:
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

    db = SessionLocal()
    document_id: int | None = None
    user_id: int | None = None
    try:
        suffix = uuid4().hex
        user = User(
            name=f"document-worker-user-{suffix}",
            api_key=f"document-worker-key-{suffix}",
        )
        db.add(user)
        db.flush()
        db.commit()
        user_id = user.id

        document = Documents(
            user_id=user_id,
            name="report.txt",
            content=None,
            source="upload",
            file_path="uploads/report.txt",
            file_type=".txt",
            file_size=20,
            sha256=f"document-worker-sha-{suffix}",
            status="pending",
        )
        db.add(document)
        db.commit()
        document_id = document.id

        # .run() 直接执行 Worker 任务主体；不会经过 Redis。
        process_document_task.run(document_id=document_id)

        db.expire_all()
        stored_document = db.get(Documents, document_id)
        chunks = (
            db.query(DocumentChunk)
            .filter(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index)
            .all()
        )

        assert stored_document is not None
        assert stored_document.status == "completed"
        assert [chunk.content for chunk in chunks] == chunk_texts
        assert [len(chunk.embedding) for chunk in chunks] == [384, 384]
        assert chunks[0].embedding[0] == 0.1
        assert chunks[1].embedding[0] == 0.2
    finally:
        db.rollback()
        if document_id is not None:
            document = db.get(Documents, document_id)
            if document is not None:
                db.delete(document)
                db.flush()
        if user_id is not None:
            user = db.get(User, user_id)
            if user is not None:
                db.delete(user)
        db.commit()
        db.close()


@pytest.mark.slow
def test_document_worker_indexes_and_retrieves_real_text_file(
    monkeypatch,
    tmp_path,
) -> None:
    storage_dir = tmp_path / "storage"
    upload_dir = storage_dir / "uploads"
    upload_dir.mkdir(parents=True)
    file_path = upload_dir / "report.txt"
    file_path.write_text(
        "Revenue decreased because operating costs increased.",
        encoding="utf-8",
    )
    settings = get_settings().model_copy(update={"storage_dir": storage_dir})
    monkeypatch.setattr(document_tasks, "get_settings", lambda: settings)

    db = SessionLocal()
    document_id: int | None = None
    user_id: int | None = None
    other_user_id: int | None = None
    try:
        suffix = uuid4().hex
        user = User(
            name=f"real-document-worker-user-{suffix}",
            api_key=f"real-document-worker-key-{suffix}",
        )
        db.add(user)
        db.flush()
        db.commit()
        user_id = user.id

        other_user = User(
            name=f"real-document-other-user-{suffix}",
            api_key=f"real-document-other-key-{suffix}",
        )
        db.add(other_user)
        db.commit()
        other_user_id = other_user.id

        document = Documents(
            user_id=user_id,
            name="report.txt",
            content=None,
            source="upload",
            file_path="uploads/report.txt",
            file_type=".txt",
            file_size=file_path.stat().st_size,
            sha256=f"real-document-worker-sha-{suffix}",
            status="pending",
        )
        db.add(document)
        db.commit()
        document_id = document.id

        process_document_task.run(document_id=document_id)

        db.expire_all()
        stored_document = db.get(Documents, document_id)
        chunks = (
            db.query(DocumentChunk)
            .filter(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index)
            .all()
        )

        assert stored_document is not None
        assert stored_document.status == "completed"
        assert stored_document.content == (
            "Revenue decreased because operating costs increased."
        )
        assert len(chunks) == 1
        assert chunks[0].content == stored_document.content
        assert chunks[0].embedding is not None
        assert len(chunks[0].embedding) == 384

        evidences = retrieve_evidence(
            db=db,
            question=stored_document.content,
            user_id=user_id,
            embedder=LocalEmbeddingProvider(),
        )
        assert [evidence.chunk_id for evidence in evidences] == [chunks[0].id]
        assert evidences[0].document_id == document_id
        assert evidences[0].content == stored_document.content

        other_user_evidences = retrieve_evidence(
            db=db,
            question=stored_document.content,
            user_id=other_user_id,
            embedder=LocalEmbeddingProvider(),
        )
        assert other_user_evidences == []
    finally:
        db.rollback()
        if document_id is not None:
            document = db.get(Documents, document_id)
            if document is not None:
                db.delete(document)
                db.flush()
        if user_id is not None:
            user = db.get(User, user_id)
            if user is not None:
                db.delete(user)
        if other_user_id is not None:
            other_user = db.get(User, other_user_id)
            if other_user is not None:
                db.delete(other_user)
        db.commit()
        db.close()
