from app.core.celery_app import celery_app
from app.core.settings import get_settings
from app.db.session import SessionLocal, set_tenant_scope
from app.modules.input_artifacts.processing_storage import get_artifact_processing_storage
from app.modules.input_artifacts.scan_worker import execute_scan_job
from app.modules.input_artifacts.scanner import ClamDScanner


@celery_app.task(name="app.modules.input_artifacts.tasks.process_scan_job")
def process_scan_job(
    company_id: int,
    job_id: int,
    dispatch_generation: int,
) -> bool:
    settings = get_settings()
    db = SessionLocal()
    try:
        set_tenant_scope(db, company_id)
        return execute_scan_job(
            db,
            job_id=job_id,
            dispatch_generation=dispatch_generation,
            processor_name="clamd",
            processor_version=settings.input_artifact_clamd_processor_version,
            scanner_factory=lambda: ClamDScanner(
                host=settings.input_artifact_clamd_host,
                port=settings.input_artifact_clamd_port,
                timeout_seconds=settings.input_artifact_clamd_timeout_seconds,
            ),
            storage_factory=lambda: get_artifact_processing_storage(settings),
        )
    finally:
        db.close()
