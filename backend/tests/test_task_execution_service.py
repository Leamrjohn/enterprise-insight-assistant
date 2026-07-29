from datetime import datetime, timedelta, timezone

from app.models.analysis_task import AnalysisTask
from app.models.task_execution_attempt import TaskExecutionAttempt
from app.services.task_execution_service import (
    claim_execution,
    checkpoint_workflow_state,
    finish_execution,
    recover_expired_executions,
    transition_execution,
)


def _task(db, user_id: int) -> AnalysisTask:
    task = AnalysisTask(
        user_id=user_id, question="销售额", status="queued", stage="queued"
    )
    db.add(task)
    db.commit()
    return task


def test_duplicate_claim_creates_one_attempt(db_session, test_user) -> None:
    task = _task(db_session, test_user.id)
    first = claim_execution(
        db_session, task_id=task.id, celery_task_id="one", worker_id="w1"
    )
    second = claim_execution(
        db_session, task_id=task.id, celery_task_id="two", worker_id="w2"
    )
    assert first is not None
    assert second is None
    assert first.attempt.workflow_version == "v1"
    assert first.attempt.heartbeat_at is not None
    assert first.attempt.latest_checkpoint_id is not None
    assert (
        db_session.query(TaskExecutionAttempt).filter_by(task_id=task.id).count() == 1
    )


def test_expired_execution_is_recoverable_and_old_execution_cannot_publish(
    db_session, test_user
) -> None:
    task = _task(db_session, test_user.id)
    old = claim_execution(
        db_session, task_id=task.id, celery_task_id="old", worker_id="w1"
    )
    assert old is not None
    old.attempt.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()
    assert recover_expired_executions(db_session) == [task.id]
    replacement = claim_execution(
        db_session, task_id=task.id, celery_task_id="new", worker_id="w2"
    )
    assert replacement is not None
    assert not finish_execution(
        db_session,
        attempt=old.attempt,
        task_status="completed",
        result_summary="stale",
        result_data={},
        error_message=None,
    )
    assert finish_execution(
        db_session,
        attempt=replacement.attempt,
        task_status="completed",
        result_summary="fresh",
        result_data={},
        error_message=None,
    )
    db_session.refresh(task)
    assert task.status == "completed"
    assert task.result_summary == "fresh"


def test_cancelled_task_rejects_execution_publish(db_session, test_user) -> None:
    task = _task(db_session, test_user.id)
    execution = claim_execution(
        db_session, task_id=task.id, celery_task_id="one", worker_id="w1"
    )
    assert execution is not None
    task.status = "cancelled"
    db_session.commit()
    assert not finish_execution(
        db_session,
        attempt=execution.attempt,
        task_status="completed",
        result_summary="must not publish",
        result_data={},
        error_message=None,
    )


def test_stale_execution_cannot_transition_task_to_failed(
    db_session, test_user
) -> None:
    task = _task(db_session, test_user.id)
    old = claim_execution(
        db_session, task_id=task.id, celery_task_id="old", worker_id="w1"
    )
    assert old is not None
    old.attempt.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()
    assert recover_expired_executions(db_session) == [task.id]
    replacement = claim_execution(
        db_session, task_id=task.id, celery_task_id="new", worker_id="w2"
    )
    assert replacement is not None

    assert (
        transition_execution(
            db_session,
            attempt=old.attempt,
            task_status="failed",
            stage="completed",
            attempt_status="failed",
            error_type="RuntimeError",
            error_message="stale worker failure",
            recovery_instruction="terminal_failure",
            next_node=None,
        )
        is None
    )
    assert finish_execution(
        db_session,
        attempt=replacement.attempt,
        task_status="completed",
        result_summary="fresh",
        result_data={},
        error_message=None,
    )
    db_session.refresh(task)
    assert task.status == "completed"
    assert task.result_summary == "fresh"


def test_retry_transition_relinquishes_attempt_and_records_recovery_checkpoint(
    db_session, test_user
) -> None:
    task = _task(db_session, test_user.id)
    execution = claim_execution(
        db_session, task_id=task.id, celery_task_id="one", worker_id="w1"
    )
    assert execution is not None

    record = transition_execution(
        db_session,
        attempt=execution.attempt,
        task_status="retrying",
        stage="retrying",
        attempt_status="retrying",
        error_type="TimeoutError",
        error_message="temporary outage",
        recovery_instruction="retry_same_execution_scope",
        next_node="planner_node",
    )
    assert record is not None
    db_session.commit()

    db_session.refresh(task)
    db_session.refresh(execution.attempt)
    assert task.status == "retrying"
    assert task.active_execution_id is None
    assert execution.attempt.status == "retrying"
    assert execution.attempt.finished_at is not None
    checkpoint = execution.attempt.checkpoints[-1]
    assert checkpoint.next_node == "planner_node"
    assert checkpoint.recovery_instruction == "retry_same_execution_scope"


def test_recovered_claim_uses_latest_completed_node_state(
    db_session, test_user
) -> None:
    task = _task(db_session, test_user.id)
    old = claim_execution(
        db_session, task_id=task.id, celery_task_id="old", worker_id="w1"
    )
    assert old is not None
    assert checkpoint_workflow_state(
        db_session,
        attempt=old.attempt,
        stage="querying_data",
        completed_node="data_node",
        next_node="knowledge_node",
        workflow_state={
            "plan": {"action": "analyze", "route": "hybrid"},
            "data_result": {"status": "ready", "evidence": [{"rows": [[1]]}]},
        },
    )
    old.attempt.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()
    assert recover_expired_executions(db_session) == [task.id]

    replacement = claim_execution(
        db_session, task_id=task.id, celery_task_id="new", worker_id="w2"
    )

    assert replacement is not None
    assert replacement.resume_next_node == "knowledge_node"
    assert replacement.resume_state == {
        "plan": {"action": "analyze", "route": "hybrid"},
        "data_result": {"status": "ready", "evidence": [{"rows": [[1]]}]},
    }
