"""Periodic publisher for durable task creation events."""

from app.core.celery_app import celery_app
from app.db.session import SessionLocal
from app.services.outbox_service import pending_event_ids, publish_analysis_task_event
from app.services.task_execution_service import recover_expired_executions


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


@celery_app.task(name="app.tasks.outbox_tasks.recover_expired_analysis_executions")
def recover_expired_analysis_executions() -> int:
    """Return expired work to the queue; the next Worker owns a fresh attempt."""
    db = SessionLocal()
    try:
        task_ids = recover_expired_executions(db)
        from app.tasks.analysis_tasks import process_analysis_task

        for task_id in task_ids:
            process_analysis_task.delay(task_id=task_id)
        return len(task_ids)
    finally:
        db.close()
