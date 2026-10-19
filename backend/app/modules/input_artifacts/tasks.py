from app.core.celery_app import celery_app
from app.core.settings import get_settings
from app.db.session import SessionLocal, set_tenant_scope
from app.modules.input_artifacts.image_ocr import TesseractImageOcr
from app.modules.input_artifacts.parse_worker import execute_parse_job
from app.modules.input_artifacts.parser import ImageParseLimits, PdfParseLimits
from app.modules.input_artifacts.pdf_render import PopplerPdfPageRenderer
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


@celery_app.task(name="app.modules.input_artifacts.tasks.process_parse_job")
def process_parse_job(
    company_id: int,
    job_id: int,
    dispatch_generation: int,
) -> bool:
    settings = get_settings()
    db = SessionLocal()
    try:
        set_tenant_scope(db, company_id)
        return execute_parse_job(
            db,
            job_id=job_id,
            dispatch_generation=dispatch_generation,
            processor_name="input-artifact-parser",
            processor_version=settings.input_artifact_parser_processor_version,
            storage_factory=lambda: get_artifact_processing_storage(settings),
            image_limits=ImageParseLimits(
                max_pixels=settings.input_artifact_image_max_pixels,
                minimum_ocr_confidence=settings.input_artifact_ocr_minimum_confidence,
            ),
            pdf_limits=PdfParseLimits(
                max_ocr_pages=settings.input_artifact_pdf_max_ocr_pages,
                minimum_ocr_confidence=settings.input_artifact_ocr_minimum_confidence,
            ),
            image_ocr=TesseractImageOcr(
                languages=settings.input_artifact_ocr_languages,
                timeout_seconds=settings.input_artifact_ocr_timeout_seconds,
            ).extract,
            pdf_page_renderer=PopplerPdfPageRenderer(
                timeout_seconds=settings.input_artifact_pdf_render_timeout_seconds,
                max_side_pixels=settings.input_artifact_pdf_render_max_side_pixels,
            ).render_page,
        )
    finally:
        db.close()
