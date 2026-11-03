"""Stage 3.2 invariants that were not yet covered by existing worker tests."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from time import sleep
from uuid import uuid4

from app.db.session import SessionLocal
from app.modules.identity.models import User
from app.modules.workflow.delivery.outbox import (
    AnalysisTaskOutboxEvent,
    claim_analysis_task_event_for_publication,
    create_analysis_task_event,
    mark_analysis_task_event_broker_accepted,
    mark_analysis_task_event_worker_claimed,
)
from app.modules.workflow.lifecycle.execution import claim_execution, finish_execution
from app.modules.workflow.lifecycle.execution_attempt import TaskExecutionAttempt
from app.modules.workflow.models import AnalysisTask
from app.modules.workflow.repository import cancel_task


def test_cancel_while_running_blocks_the_late_terminal_write(
    db_session, test_user
) -> None:
    """H5: once cancelled, the still-running Worker must not persist any result."""
    task = AnalysisTask(
        user_id=test_user.id, question="cancel mid-run", status="queued", stage="queued"
    )
    db_session.add(task)
    db_session.commit()
    execution = claim_execution(
        db_session, task_id=task.id, celery_task_id="c1", worker_id="w1"
    )
    assert execution is not None

    cancel_task(db_session, task)
    db_session.commit()
    published = finish_execution(
        db_session,
        attempt=execution.attempt,
        task_status="completed",
        result_summary="late summary",
        result_data={"report": {"status": "completed"}},
        error_message=None,
    )
    db_session.commit()

    db_session.refresh(task)
    assert published is False
    assert task.status == "cancelled"
    assert "report" not in (task.result_data or {})


def test_concurrent_deliveries_create_exactly_one_execution(
    migrated_test_database: None,
) -> None:
    """H4/H6 precondition: racing Workers on real PostgreSQL yield one owner."""
    suffix = uuid4().hex
    setup = SessionLocal()
    try:
        user = User(name=f"claim-race-{suffix}", api_key=f"claim-race-{suffix}")
        setup.add(user)
        setup.flush()
        task = AnalysisTask(
            user_id=user.id, question="claim race", status="queued", stage="queued"
        )
        setup.add(task)
        setup.commit()
        user_id, task_id = user.id, task.id
    finally:
        setup.close()

    workers = 4
    barrier = Barrier(workers)

    def deliver(index: int) -> bool:
        db = SessionLocal()
        try:
            barrier.wait(timeout=5)
            return (
                claim_execution(
                    db,
                    task_id=task_id,
                    celery_task_id=f"delivery-{index}",
                    worker_id=f"worker-{index}",
                )
                is not None
            )
        finally:
            db.close()

    try:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            claimed = list(executor.map(deliver, range(workers)))
        check = SessionLocal()
        try:
            attempts = (
                check.query(TaskExecutionAttempt)
                .filter(TaskExecutionAttempt.task_id == task_id)
                .count()
            )
        finally:
            check.close()

        assert claimed.count(True) == 1
        assert attempts == 1
    finally:
        cleanup = SessionLocal()
        try:
            cleanup.query(AnalysisTask).filter(AnalysisTask.id == task_id).delete()
            cleanup.query(User).filter(User.id == user_id).delete()
            cleanup.commit()
        finally:
            cleanup.close()


def test_publisher_and_fast_worker_do_not_deadlock(
    migrated_test_database: None,
) -> None:
    """A Worker holding the task row settles the event the publisher is recording."""
    suffix = uuid4().hex
    setup = SessionLocal()
    try:
        user = User(name=f"lock-order-{suffix}", api_key=f"lock-order-{suffix}")
        setup.add(user)
        setup.flush()
        task = AnalysisTask(
            user_id=user.id, question="lock order", status="queued", stage="queued"
        )
        setup.add(task)
        setup.flush()
        event = create_analysis_task_event(setup, task_id=task.id)
        setup.commit()
        user_id, task_id, event_id = user.id, task.id, event.id
        claim = claim_analysis_task_event_for_publication(setup, event_id=event_id)
        assert claim is not None
    finally:
        setup.close()

    def publisher_records_acceptance() -> bool:
        db = SessionLocal()
        try:
            return mark_analysis_task_event_broker_accepted(
                db, claim=claim, broker_message_id="broker-message"
            )
        finally:
            db.close()

    worker = SessionLocal()
    try:
        # The order claim_execution uses: the task row first, then the event.
        worker.get(AnalysisTask, task_id, with_for_update=True)
        with ThreadPoolExecutor(max_workers=1) as executor:
            accepted = executor.submit(publisher_records_acceptance)
            sleep(0.3)  # Let the publisher take whatever locks it takes first.
            assert mark_analysis_task_event_worker_claimed(
                worker, task_id=task_id, execution_id="worker-execution"
            )
            worker.commit()
            assert accepted.result(timeout=10) is False

        check = SessionLocal()
        try:
            status = check.get(AnalysisTaskOutboxEvent, event_id).status
        finally:
            check.close()
        assert status == "worker_claimed"
    finally:
        worker.rollback()
        worker.close()
        cleanup = SessionLocal()
        try:
            cleanup.query(AnalysisTaskOutboxEvent).filter(
                AnalysisTaskOutboxEvent.id == event_id
            ).delete()
            cleanup.query(AnalysisTask).filter(AnalysisTask.id == task_id).delete()
            cleanup.query(User).filter(User.id == user_id).delete()
            cleanup.commit()
        finally:
            cleanup.close()
