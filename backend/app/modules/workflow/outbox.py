"""Reliable publication for analysis task outbox events."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, cast

from app.db.clock import database_now
from app.modules.workflow.outbox_models import AnalysisTaskOutboxEvent
from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

ANALYSIS_TASK_CREATED = "analysis_task.created"
PUBLISH_LEASE_SECONDS = 30
DELIVERY_LEASE_SECONDS = 120


@dataclass(frozen=True, slots=True)
class ClaimedAnalysisTaskPublication:
    event_id: int
    task_id: int
    execution_id: str
    generation: int


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
    """Publish one claimed event; broker acceptance is not Worker delivery."""
    claim = claim_analysis_task_event_for_publication(db, event_id=event_id)
    if claim is None:
        return False
    event = db.get(AnalysisTaskOutboxEvent, claim.event_id)
    assert event is not None
    if event.event_type != ANALYSIS_TASK_CREATED:
        raise ValueError(f"unsupported outbox event type: {event.event_type}")

    task_id = event.payload.get("task_id")
    if not isinstance(task_id, int):
        raise ValueError("analysis task outbox event is missing task_id")

    enqueue_task = enqueue
    if enqueue_task is None:
        # Import lazily to avoid a service <-> Celery module import cycle.
        from app.modules.workflow.tasks import process_analysis_task

        def _enqueue(value: int) -> object:
            return cast(Any, process_analysis_task).delay(task_id=value)

        enqueue_task = _enqueue

    try:
        async_result = enqueue_task(claim.task_id)
        celery_task_id = getattr(async_result, "id", None)
        if not isinstance(celery_task_id, str) or not celery_task_id.strip():
            return return_analysis_task_event_to_pending(
                db, claim=claim, failure_code="broker_publish_invalid_result"
            )
        return mark_analysis_task_event_broker_accepted(
            db, claim=claim, broker_message_id=celery_task_id
        )
    except Exception as exc:
        return_analysis_task_event_to_pending(
            db,
            claim=claim,
            failure_code=f"{type(exc).__name__}: {exc}"[:2000],
        )
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
    now = database_now(db)
    return [
        event_id
        for (event_id,) in (
            db.query(AnalysisTaskOutboxEvent.id)
            .filter(
                or_(
                    AnalysisTaskOutboxEvent.status == "pending",
                    and_(
                        AnalysisTaskOutboxEvent.status == "publishing",
                        AnalysisTaskOutboxEvent.publish_lease_expires_at
                        <= now,
                    ),
                    and_(
                        AnalysisTaskOutboxEvent.status == "broker_accepted",
                        AnalysisTaskOutboxEvent.publish_lease_expires_at
                        <= now,
                    ),
                )
            )
            .order_by(AnalysisTaskOutboxEvent.id)
            .limit(limit)
            .all()
        )
    ]


def claim_analysis_task_event_for_publication(
    db: Session, *, event_id: int, lease_seconds: int = PUBLISH_LEASE_SECONDS
) -> ClaimedAnalysisTaskPublication | None:
    now = database_now(db)
    from uuid import uuid4

    execution_id = str(uuid4())
    event = (
        db.execute(
            update(AnalysisTaskOutboxEvent)
            .where(
                AnalysisTaskOutboxEvent.id == event_id,
                or_(
                    AnalysisTaskOutboxEvent.status == "pending",
                    and_(
                        AnalysisTaskOutboxEvent.status == "publishing",
                        AnalysisTaskOutboxEvent.publish_lease_expires_at <= now,
                    ),
                    and_(
                        AnalysisTaskOutboxEvent.status == "broker_accepted",
                        AnalysisTaskOutboxEvent.publish_lease_expires_at <= now,
                    ),
                ),
            )
            .values(
                status="publishing",
                publish_generation=AnalysisTaskOutboxEvent.publish_generation + 1,
                publish_execution_id=execution_id,
                publish_lease_expires_at=now + timedelta(seconds=lease_seconds),
                last_error=None,
            )
            .returning(
                AnalysisTaskOutboxEvent.id,
                AnalysisTaskOutboxEvent.task_id,
                AnalysisTaskOutboxEvent.publish_generation,
            )
        )
        .mappings()
        .one_or_none()
    )
    if event is None:
        db.rollback()
        return None
    db.commit()
    return ClaimedAnalysisTaskPublication(
        event["id"], event["task_id"], execution_id, event["publish_generation"]
    )


def mark_analysis_task_event_broker_accepted(
    db: Session, *, claim: ClaimedAnalysisTaskPublication, broker_message_id: str
) -> bool:
    now = database_now(db)
    updated = db.scalar(
        update(AnalysisTaskOutboxEvent)
        .where(
            AnalysisTaskOutboxEvent.id == claim.event_id,
            AnalysisTaskOutboxEvent.status == "publishing",
            AnalysisTaskOutboxEvent.publish_execution_id == claim.execution_id,
            AnalysisTaskOutboxEvent.publish_generation == claim.generation,
            AnalysisTaskOutboxEvent.publish_lease_expires_at > now,
        )
        .values(
            status="broker_accepted",
            broker_message_id=broker_message_id.strip(),
            broker_accepted_at=now,
            publish_execution_id=None,
            publish_lease_expires_at=now + timedelta(seconds=DELIVERY_LEASE_SECONDS),
            publish_attempt_count=AnalysisTaskOutboxEvent.publish_attempt_count + 1,
        )
        .returning(AnalysisTaskOutboxEvent.id)
    )
    if updated is None:
        db.rollback()
        return False
    from app.modules.workflow.models import AnalysisTask

    task = db.get(AnalysisTask, claim.task_id)
    if task is not None:
        task.celery_task_id = broker_message_id.strip()
    db.commit()
    return True


def return_analysis_task_event_to_pending(
    db: Session, *, claim: ClaimedAnalysisTaskPublication, failure_code: str
) -> bool:
    updated = db.scalar(
        update(AnalysisTaskOutboxEvent)
        .where(
            AnalysisTaskOutboxEvent.id == claim.event_id,
            AnalysisTaskOutboxEvent.status == "publishing",
            AnalysisTaskOutboxEvent.publish_execution_id == claim.execution_id,
            AnalysisTaskOutboxEvent.publish_generation == claim.generation,
        )
        .values(
            status="pending",
            publish_execution_id=None,
            publish_lease_expires_at=None,
            last_error=failure_code,
            publish_attempt_count=AnalysisTaskOutboxEvent.publish_attempt_count + 1,
        )
        .returning(AnalysisTaskOutboxEvent.id)
    )
    if updated is None:
        db.rollback()
        return False
    db.commit()
    return True


def mark_analysis_task_event_worker_claimed(
    db: Session, *, task_id: int, execution_id: str
) -> bool:
    now = database_now(db)
    updated = db.scalar(
        update(AnalysisTaskOutboxEvent)
        .where(
            AnalysisTaskOutboxEvent.task_id == task_id,
            AnalysisTaskOutboxEvent.status == "broker_accepted",
        )
        .values(
            status="worker_claimed",
            worker_execution_id=execution_id,
            worker_claimed_at=now,
            publish_lease_expires_at=None,
            last_error=None,
        )
        .returning(AnalysisTaskOutboxEvent.id)
    )
    return updated is not None


def cancel_unclaimed_analysis_task_event(db: Session, *, task_id: int) -> bool:
    """Make cancellation terminal for an event that has no effective Worker claim."""
    updated = db.scalar(
        update(AnalysisTaskOutboxEvent)
        .where(
            AnalysisTaskOutboxEvent.task_id == task_id,
            AnalysisTaskOutboxEvent.status.in_(
                ("pending", "publishing", "broker_accepted")
            ),
        )
        .values(
            status="cancelled",
            publish_execution_id=None,
            publish_lease_expires_at=None,
            last_error="task_cancelled_before_worker_claim",
        )
        .returning(AnalysisTaskOutboxEvent.id)
    )
    return updated is not None


def reconcile_unclaimed_broker_accepted_events(db: Session, *, limit: int = 100) -> list[int]:
    now = database_now(db)
    return [
        event_id
        for (event_id,) in db.execute(
            select(AnalysisTaskOutboxEvent.id)
            .where(
                AnalysisTaskOutboxEvent.status == "broker_accepted",
                AnalysisTaskOutboxEvent.publish_lease_expires_at <= now,
            )
            .order_by(AnalysisTaskOutboxEvent.id)
            .limit(limit)
        )
    ]
