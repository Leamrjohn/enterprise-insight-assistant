from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import app.modules.workflow.outbox as outbox_module
from app.modules.workflow.execution import claim_execution
from app.modules.workflow.models import AnalysisTask
from app.modules.workflow.outbox import (
    cancel_unclaimed_analysis_task_event,
    create_analysis_task_event,
    pending_event_ids,
    publish_analysis_task_event,
    reconcile_unclaimed_broker_accepted_events,
)


def test_outbox_keeps_failed_publish_pending_and_republishes(db_session, test_user):
    task = AnalysisTask(
        user_id=test_user.id,
        question="华东区销售额为什么下降？",
        status="queued",
        stage="queued",
    )
    db_session.add(task)
    db_session.flush()
    event = create_analysis_task_event(db_session, task_id=task.id)
    db_session.commit()

    def fail_enqueue(task_id: int):
        raise ConnectionError(f"redis unavailable for task {task_id}")

    assert (
        publish_analysis_task_event(db_session, event_id=event.id, enqueue=fail_enqueue)
        is False
    )
    db_session.refresh(event)
    assert event.status == "pending"
    assert event.publish_attempt_count == 1
    assert "ConnectionError" in (event.last_error or "")
    assert pending_event_ids(db_session) == [event.id]

    published_task_ids: list[int] = []

    def succeed_enqueue(task_id: int):
        published_task_ids.append(task_id)
        return SimpleNamespace(id="celery-test-id")

    assert (
        publish_analysis_task_event(
            db_session, event_id=event.id, enqueue=succeed_enqueue
        )
        is True
    )
    db_session.refresh(event)
    db_session.refresh(task)
    assert published_task_ids == [task.id]
    assert event.status == "broker_accepted"
    assert event.publish_attempt_count == 2
    assert event.last_error is None
    assert task.celery_task_id == "celery-test-id"
    assert pending_event_ids(db_session) == []

    execution = claim_execution(
        db_session,
        task_id=task.id,
        celery_task_id="celery-test-id",
        worker_id="outbox-delivery-test",
    )
    assert execution is not None
    db_session.refresh(event)
    assert event.status == "worker_claimed"
    assert event.worker_execution_id == execution.attempt.execution_id


def test_outbox_delivery_lease_uses_database_time(db_session, test_user, monkeypatch):
    database_time = datetime(2040, 1, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(outbox_module, "database_now", lambda _db: database_time)
    task = AnalysisTask(
        user_id=test_user.id,
        question="outbox clock",
        status="queued",
        stage="queued",
    )
    db_session.add(task)
    db_session.flush()
    event = create_analysis_task_event(db_session, task_id=task.id)
    db_session.commit()

    assert publish_analysis_task_event(
        db_session, event_id=event.id, enqueue=lambda _task_id: SimpleNamespace(id="clock")
    )

    db_session.refresh(event)
    assert event.broker_accepted_at == database_time
    assert event.publish_lease_expires_at == database_time + timedelta(seconds=120)


def test_broker_accepted_event_is_republished_only_after_delivery_lease_expires(
    db_session, test_user
):
    task = AnalysisTask(
        user_id=test_user.id,
        question="outbox lease reconciliation",
        status="queued",
        stage="queued",
    )
    db_session.add(task)
    db_session.flush()
    event = create_analysis_task_event(db_session, task_id=task.id)
    db_session.commit()
    deliveries: list[int] = []

    def enqueue(task_id: int):
        deliveries.append(task_id)
        return SimpleNamespace(id=f"broker-{len(deliveries)}")

    assert publish_analysis_task_event(db_session, event_id=event.id, enqueue=enqueue)
    db_session.refresh(event)
    assert event.status == "broker_accepted"
    assert pending_event_ids(db_session) == []

    event.publish_lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()
    assert pending_event_ids(db_session) == [event.id]
    assert publish_analysis_task_event(db_session, event_id=event.id, enqueue=enqueue)
    db_session.refresh(event)
    assert deliveries == [task.id, task.id]
    assert event.status == "broker_accepted"
    assert event.publish_attempt_count == 2


def test_cancelled_unclaimed_event_is_not_republished(
    db_session, test_user
) -> None:
    task = AnalysisTask(
        user_id=test_user.id,
        question="cancel before worker claim",
        status="queued",
        stage="queued",
    )
    db_session.add(task)
    db_session.flush()
    event = create_analysis_task_event(db_session, task_id=task.id)
    db_session.commit()

    assert publish_analysis_task_event(
        db_session,
        event_id=event.id,
        enqueue=lambda _task_id: SimpleNamespace(id="broker-cancelled"),
    )
    assert cancel_unclaimed_analysis_task_event(db_session, task_id=task.id)
    db_session.commit()

    db_session.refresh(event)
    assert event.status == "cancelled"
    assert event.publish_lease_expires_at is None
    assert event.last_error == "task_cancelled_before_worker_claim"
    assert pending_event_ids(db_session) == []
    assert reconcile_unclaimed_broker_accepted_events(db_session) == []
    assert not publish_analysis_task_event(
        db_session,
        event_id=event.id,
        enqueue=lambda _task_id: SimpleNamespace(id="must-not-enqueue"),
    )
