"""验证两个真实 Celery Worker 重复消费同一文档任务时的入库结果。"""

from __future__ import annotations

import time
from uuid import uuid4

from app.core.settings import get_settings
from app.db.session import SessionLocal
from app.models.document_chunk import DocumentChunk
from app.models.documents import Documents
from app.models.user import User
from app.tasks.document_tasks import process_document_task


def wait_for_result(result, *, timeout_seconds: int) -> None:
    deadline = time.monotonic() + timeout_seconds
    while not result.ready():
        if time.monotonic() >= deadline:
            raise TimeoutError("Celery worker did not finish document ingestion in time")
        time.sleep(0.5)
    result.get(timeout=1, propagate=True)


def main() -> None:
    settings = get_settings()
    db = SessionLocal()
    document_id: int | None = None
    user_id: int | None = None
    file_path = None

    try:
        suffix = uuid4().hex
        file_path = settings.upload_dir / f"e2e-document-{suffix}.txt"
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_content = "Revenue decreased because operating costs increased."
        file_path.write_text(file_content, encoding="utf-8")

        user = User(
            name=f"e2e-document-user-{suffix}",
            api_key=f"e2e-document-key-{suffix}",
        )
        db.add(user)
        db.flush()
        db.commit()
        user_id = user.id

        document = Documents(
            user_id=user_id,
            name=file_path.name,
            content=None,
            source="upload",
            file_path=str(file_path.relative_to(settings.storage_dir)),
            file_type=".txt",
            file_size=file_path.stat().st_size,
            sha256=f"e2e-document-sha-{suffix}",
            status="pending",
        )
        db.add(document)
        db.commit()
        document_id = document.id

        first_result = process_document_task.apply_async(
            kwargs={"document_id": document_id}
        )
        second_result = process_document_task.apply_async(
            kwargs={"document_id": document_id}
        )

        wait_for_result(first_result, timeout_seconds=180)
        wait_for_result(second_result, timeout_seconds=180)

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
        assert stored_document.content == file_content
        assert len(chunks) == 1
        assert chunks[0].content == file_content
        assert chunks[0].embedding is not None
        assert len(chunks[0].embedding) == 384

        print(
            "E2E document ingestion passed: "
            f"document_id={document_id}, chunks={len(chunks)}, "
            f"embedding_dimension={len(chunks[0].embedding)}"
        )
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
        if file_path is not None:
            file_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
