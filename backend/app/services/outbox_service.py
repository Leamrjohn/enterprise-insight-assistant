"""Reliable publication for analysis task outbox events."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy.orm import Session

from app.models.outbox import AnalysisTaskOutboxEvent

logger = logging.getLogger(__name__)

ANALYSIS_TASK_CREATED = "analysis_task.created"


def create_analysis_task_event(db: Session, *, task_id: int) -> AnalysisTaskOutboxEvent:
    event = AnalysisTaskOutboxEvent(
        task_id=task_id,
        event_type=ANALYSIS_TASK_CREATED,
        payload={"task_id": task_id},
        status="pending",
    )
    db.add(event)
    db.flush()
    return event


def publish_analysis_task_event(
    db: Session,
    *,
    event_id: int,
    enqueue: Callable[[int], object] | None = None,
) -> bool:
    """Attempt publication once; leave failures pending for the periodic publisher."""
    event = db.get(AnalysisTaskOutboxEvent, event_id)
    if event is None or event.status == "published":
        return event is not None
    if event.event_type != ANALYSIS_TASK_CREATED:
        raise ValueError(f"unsupported outbox event type: {event.event_type}")

    task_id = event.payload.get("task_id")
    if not isinstance(task_id, int):
        raise ValueError("analysis task outbox event is missing task_id")

    if enqueue is None:
        # Import lazily to avoid a service <-> Celery module import cycle.
        from app.tasks.analysis_tasks import process_analysis_task

        def enqueue(value: int) -> object:
            return process_analysis_task.delay(task_id=value)

    event.publish_attempt_count += 1
    try:
        async_result = enqueue(task_id)
        event.status = "published"
        event.published_at = datetime.now(timezone.utc)
        event.last_error = None
        celery_task_id = getattr(async_result, "id", None)
        if isinstance(celery_task_id, str):
            event_task = event.task_id
            # The Worker records the final execution id when it claims the task.
            from app.models.analysis_task import AnalysisTask

            task = db.get(AnalysisTask, event_task)
            if task is not None:
                task.celery_task_id = celery_task_id
        db.commit()
        return True
    except Exception as exc:
        event.last_error = f"{type(exc).__name__}: {exc}"[:2000]
        db.commit()
        logger.warning(
            "Analysis task outbox publication failed; event remains pending",
            extra={
                "outbox_event_id": event.id,
                "task_id": task_id,
                "error_type": type(exc).__name__,
            },
        )
        return False


def pending_event_ids(db: Session, *, limit: int = 100) -> list[int]:
    return [
        event_id
        for (event_id,) in (
            db.query(AnalysisTaskOutboxEvent.id)
            .filter(AnalysisTaskOutboxEvent.status == "pending")
            .order_by(AnalysisTaskOutboxEvent.id)
            .limit(limit)
            .all()
        )
    ]
