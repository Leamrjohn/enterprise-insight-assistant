"""Stage 3.2 invariants that were not yet covered by existing worker tests."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

from app.db.session import SessionLocal
from app.modules.identity.models import User
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
