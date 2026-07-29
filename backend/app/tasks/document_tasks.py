import logging

from app.core.celery_app import celery_app
from app.core.settings import get_settings
from app.db.session import SessionLocal, set_tenant_scope
from app.models.documents import Documents
from app.services.document_ingestion_service import process_document_chunks
from sqlalchemy import update

logger = logging.getLogger(__name__)


@celery_app.task
def process_document_task(document_id: int, company_id: int) -> None:
    """异步切分文档并生成、保存 Embedding。"""
    db = SessionLocal()
    try:
        set_tenant_scope(db, company_id)
        document = db.get(Documents, document_id)
        if document is None or document.company_id != company_id:
            logger.error("Document %s not found", document_id)
            return

        claimed_document_id = db.execute(
            update(Documents)
            .where(
                Documents.id == document_id,
                Documents.status == "pending",
            )
            .values(
                status="processing",
                error_message=None,
            )
            .returning(Documents.id)
        ).scalar_one_or_none()

        if claimed_document_id is None:
            logger.info(
                "Document %s is no longer pending; skipping duplicate task",
                document_id,
            )
            return

        db.commit()
        db.refresh(document)
        process_document_chunks(
            db=db,
            document=document,
            settings=get_settings(),
        )

    except Exception:
        logger.exception(
            "Document ingestion task failed", extra={"document_id": document_id}
        )
        raise
    finally:
        db.close()
