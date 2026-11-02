"""Daily memory cleanup, one company at a time so one failure stays contained."""

import logging

from app.core.celery_app import celery_app
from app.db.session import SessionLocal, set_tenant_scope
from app.modules.memory.service import cleanup_memories
from app.modules.organizations.models import Company
from sqlalchemy import select

logger = logging.getLogger(__name__)


@celery_app.task(name="app.modules.memory.tasks.cleanup_expired_memories")
def cleanup_expired_memories() -> dict[str, int]:
    totals = {"soft_deleted": 0, "purged": 0, "failed_companies": 0}
    with SessionLocal() as db:
        company_ids = db.execute(select(Company.id)).scalars().all()
    for company_id in company_ids:
        with SessionLocal() as db:
            try:
                set_tenant_scope(db, company_id)
                result = cleanup_memories(db, company_id=company_id)
                db.commit()
            except Exception:
                db.rollback()
                totals["failed_companies"] += 1
                logger.exception(
                    "Memory cleanup failed", extra={"company_id": company_id}
                )
                continue
        totals["soft_deleted"] += result["soft_deleted"]
        totals["purged"] += result["purged"]
    logger.info("Memory cleanup finished", extra=totals)
    return totals
