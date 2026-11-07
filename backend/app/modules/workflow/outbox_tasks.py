"""Periodic publisher for durable task creation events."""

import logging
from datetime import timedelta
from typing import Any, cast

from app.core.celery_app import celery_app
from app.db.session import SessionLocal
from app.modules.workflow.delivery.outbox import (
    pending_event_ids,
    publish_analysis_task_event,
)
from app.modules.workflow.lifecycle.execution import (
    recover_expired_executions,
    settle_stranded_task,
    stranded_retrying_task_ids,
)
from app.modules.workflow.models import AnalysisTask

logger = logging.getLogger(__name__)
# Longer than one Beat recovery cycle, so a delivery still in flight is not doubled.
STRANDED_RETRY_AFTER = timedelta(minutes=2)
# Dead letter: whichever limit is reached first fails the task.
MAX_STRANDED_REDELIVERIES = 10
MAX_STRANDED_DURATION = timedelta(minutes=30)


def _deliver(task_ids: list[int]) -> int:
    """Queue each task on its own so one broker failure cannot strand the rest."""
    from app.modules.workflow.tasks import process_analysis_task

    delivered = 0
    for task_id in task_ids:
        try:
            cast(Any, process_analysis_task).delay(task_id=task_id)
        except Exception as exc:  # noqa: BLE001 - reconcile redelivers it later
            logger.warning(
                "Analysis task delivery failed; task stays retrying",
                extra={"task_id": task_id, "error_type": type(exc).__name__},
            )
            continue
        delivered += 1
    return delivered


@celery_app.task(
    name="app.modules.workflow.outbox_tasks.publish_pending_analysis_task_events"
)
def publish_pending_analysis_task_events() -> int:
    db = SessionLocal()
    try:
        event_ids = pending_event_ids(db)
        return sum(
            publish_analysis_task_event(db, event_id=event_id) for event_id in event_ids
        )
    finally:
        db.close()


@celery_app.task(
    name="app.modules.workflow.outbox_tasks.recover_expired_analysis_executions"
)
def recover_expired_analysis_executions() -> dict[str, int]:
    """Return expired work to the queue; the next Worker owns a fresh attempt."""
    db = SessionLocal()
    try:
        task_ids = recover_expired_executions(db)
    finally:
        db.close()
    return {"recovered": len(task_ids), "delivered": _deliver(task_ids)}


@celery_app.task(
    name="app.modules.workflow.outbox_tasks.reconcile_stranded_analysis_tasks"
)
def reconcile_stranded_analysis_tasks() -> dict[str, int]:
    """Redeliver retrying tasks whose recovery delivery never reached a Worker."""
    from app.modules.workflow.tasks import (
        GENERIC_WORKER_FAILURE_MESSAGE,
        _sync_assistant_message,
    )

    db = SessionLocal()
    redeliver: list[int] = []
    exhausted = 0
    try:
        task_ids = stranded_retrying_task_ids(db, older_than=STRANDED_RETRY_AFTER)
        for task_id in task_ids:
            outcome = settle_stranded_task(
                db,
                task_id=task_id,
                max_redeliveries=MAX_STRANDED_REDELIVERIES,
                max_stranded=MAX_STRANDED_DURATION,
            )
            if outcome == "redeliver":
                redeliver.append(task_id)
            elif outcome == "exhausted":
                _sync_assistant_message(
                    db,
                    db.get(AnalysisTask, task_id),
                    status="failed",
                    content=GENERIC_WORKER_FAILURE_MESSAGE,
                )
                exhausted += 1
                logger.error(
                    "Analysis task delivery exhausted; task failed",
                    extra={"task_id": task_id, "error_code": "delivery_exhausted"},
                )
            # One commit per task keeps each row lock short.
            db.commit()
    finally:
        db.close()
    return {
        "stranded": len(task_ids),
        "exhausted": exhausted,
        "delivered": _deliver(redeliver),
    }
