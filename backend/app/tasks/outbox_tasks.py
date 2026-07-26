"""Periodic publisher for durable task creation events."""

from app.core.celery_app import celery_app
from app.db.session import SessionLocal
from app.services.outbox_service import pending_event_ids, publish_analysis_task_event


@celery_app.task(name="app.tasks.outbox_tasks.publish_pending_analysis_task_events")
def publish_pending_analysis_task_events() -> int:
    db = SessionLocal()
    try:
        event_ids = pending_event_ids(db)
        return sum(
            publish_analysis_task_event(db, event_id=event_id) for event_id in event_ids
        )
    finally:
        db.close()
