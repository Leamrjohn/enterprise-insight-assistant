"""Periodic publisher for durable input-artifact processing events."""

from typing import Any, cast

from app.core.celery_app import celery_app
from app.db.session import SessionLocal, set_tenant_scope
from app.modules.input_artifacts.processing.processing_outbox import (
    pending_artifact_processing_event_ids,
    publish_artifact_processing_event,
)
from app.modules.input_artifacts.models import (
    ArtifactProcessingJob,
    ArtifactProcessingOutboxEvent,
)
from app.modules.organizations.models import Company
from sqlalchemy import select


@celery_app.task(
    name="app.modules.input_artifacts.outbox_tasks.publish_pending_artifact_processing_events"
)
def publish_pending_artifact_processing_events() -> int:
    db = SessionLocal()
    try:
        company_ids = db.scalars(select(Company.id).order_by(Company.id)).all()
        published_count = 0
        from app.modules.input_artifacts.tasks import process_parse_job, process_scan_job

        for company_id in company_ids:
            set_tenant_scope(db, company_id)
            event_ids = pending_artifact_processing_event_ids(db)
            for event_id in event_ids:
                event = db.get(ArtifactProcessingOutboxEvent, event_id)
                event_job = (
                    db.get(ArtifactProcessingJob, event.job_id)
                    if event is not None
                    else None
                )
                if event_job is None:
                    continue
                task = (
                    process_scan_job
                    if event_job.stage == "scan"
                    else process_parse_job
                    if event_job.stage == "parse"
                    else None
                )
                if task is None:
                    continue
                published_count += publish_artifact_processing_event(
                    db,
                    event_id=event_id,
                    enqueue=lambda company_id, job_id, dispatch_generation: cast(
                        Any, task
                    ).delay(
                        company_id=company_id,
                        job_id=job_id,
                        dispatch_generation=dispatch_generation,
                    ),
                )
        return published_count
    finally:
        db.close()
