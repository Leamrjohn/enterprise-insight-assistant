from datetime import datetime, timedelta, timezone

import app.modules.workflow.lifecycle.execution as execution_module
from app.db.clock import database_now
from app.modules.workflow.lifecycle.checkpoint import WorkflowCheckpoint
from app.modules.workflow.audit.events_models import WorkflowEvent
from app.modules.workflow.lifecycle.execution import (
    checkpoint_workflow_state,
    claim_execution,
    execution_heartbeat_interval_seconds,
    finish_execution,
    recover_expired_executions,
    renew_execution_lease,
    transition_execution,
)
from app.modules.workflow.lifecycle.execution_attempt import TaskExecutionAttempt
from app.modules.workflow.audit.model_call import ModelCallRecord
from app.modules.workflow.models import AnalysisTask
from app.modules.workflow.repository import cancel_task
from sqlalchemy import func, select


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
    rejection = (
        db_session.query(WorkflowEvent)
        .filter_by(
            execution_attempt_id=first.attempt.id,
            event_type="execution_claim_rejected",
        )
        .one()
    )
    assert rejection.error_code == "execution_already_claimed"
    assert rejection.details == {"operation": "claim_execution"}


def test_claim_uses_database_time_for_the_lease(db_session, test_user, monkeypatch) -> None:
    database_time = datetime(2040, 1, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(execution_module, "database_now", lambda _db: database_time)
    task = _task(db_session, test_user.id)

    claimed = claim_execution(
        db_session, task_id=task.id, celery_task_id="clock", worker_id="w1"
    )

    assert claimed is not None
    assert claimed.attempt.heartbeat_at == database_time
    assert claimed.attempt.lease_expires_at == database_time + timedelta(seconds=120)


def test_database_clock_advances_inside_one_transaction(db_session) -> None:
    first = database_now(db_session)
    db_session.execute(select(func.pg_sleep(0.01)))
    second = database_now(db_session)

    assert second > first


def test_heartbeat_renews_only_a_live_owned_execution(db_session, test_user) -> None:
    task = _task(db_session, test_user.id)
    execution = claim_execution(
        db_session, task_id=task.id, celery_task_id="one", worker_id="w1"
    )
    assert execution is not None
    old_expiry = execution.attempt.lease_expires_at

    assert renew_execution_lease(
        db_session, task_id=task.id, execution_id=execution.attempt.execution_id
    )

    db_session.refresh(execution.attempt)
    assert execution.attempt.heartbeat_at > execution.attempt.started_at
    assert execution.attempt.lease_expires_at > old_expiry


def test_heartbeat_rejects_an_expired_execution(db_session, test_user) -> None:
    task = _task(db_session, test_user.id)
    execution = claim_execution(
        db_session, task_id=task.id, celery_task_id="one", worker_id="w1"
    )
    assert execution is not None
    execution.attempt.lease_expires_at = datetime.now(timezone.utc) - timedelta(
        seconds=1
    )
    db_session.commit()

    assert not renew_execution_lease(
        db_session, task_id=task.id, execution_id=execution.attempt.execution_id
    )
    assert recover_expired_executions(db_session) == [task.id]


def test_heartbeat_interval_tracks_the_current_lease_setting(monkeypatch) -> None:
    monkeypatch.setattr(execution_module, "LEASE_SECONDS", 2)

    assert execution_heartbeat_interval_seconds() == 1


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
    assert finish_execution(
        db_session,
        attempt=replacement.attempt,
        task_status="completed",
        result_summary="fresh",
        result_data={},
        error_message=None,
    )
    assert not finish_execution(
        db_session,
        attempt=old.attempt,
        task_status="completed",
        result_summary="stale",
        result_data={},
        error_message=None,
    )
    db_session.refresh(task)
    assert task.status == "completed"
    assert task.result_summary == "fresh"
    event = (
        db_session.query(WorkflowEvent)
        .filter_by(
            execution_attempt_id=old.attempt.id,
            event_type="execution_write_rejected",
        )
        .one()
    )
    assert event.error_code == "execution_fence_lost"


def test_expired_execution_marks_unsettled_model_reservation_unknown(
    db_session, test_user
) -> None:
    task = _task(db_session, test_user.id)
    task.model_budget_usage = {"reserved_cost": "0.001664", "unknown_cost_calls": 0}
    old = claim_execution(
        db_session, task_id=task.id, celery_task_id="old", worker_id="w1"
    )
    assert old is not None
    reservation = ModelCallRecord(
        task_id=task.id,
        execution_attempt_id=old.attempt.id,
        node_name="planner",
        provider="test",
        model_name="test-model",
        billing_status="reserved",
        reserved_cost=0.001664,
        result_category="reserved",
    )
    db_session.add(reservation)
    old.attempt.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()

    assert recover_expired_executions(db_session) == [task.id]
    db_session.refresh(reservation)
    db_session.refresh(task)

    assert reservation.billing_status == "unknown"
    assert reservation.result_category == "unknown"
    assert reservation.error_code == "execution_lease_expired_before_settlement"
    assert reservation.settled_at is not None
    assert task.model_budget_usage == {
        "reserved_cost": "0.001664",
        "unknown_cost_calls": 1,
    }
    assert recover_expired_executions(db_session) == []
    db_session.refresh(task)
    assert task.model_budget_usage["unknown_cost_calls"] == 1


def test_resume_rejects_checkpoint_when_frozen_task_contract_changes(
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
        stage="planning",
        completed_node="planner_node",
        next_node="data_node",
        workflow_state={"plan": {"action": "analyze", "route": "data_only"}},
    )
    task.question = "a changed task contract"
    old.attempt.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()

    assert recover_expired_executions(db_session) == [task.id]
    replacement = claim_execution(
        db_session, task_id=task.id, celery_task_id="new", worker_id="w2"
    )
    assert replacement is not None
    assert replacement.resume_next_node is None
    assert replacement.resume_state is None
    event = (
        db_session.query(WorkflowEvent)
        .filter_by(
            execution_attempt_id=replacement.attempt.id,
            event_type="checkpoint_resume_rejected",
        )
        .one()
    )
    assert event.details == {"reason": "checkpoint_input_contract_changed"}


def test_resume_rejects_unsupported_checkpoint_schema(
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
        stage="planning",
        completed_node="planner_node",
        next_node="data_node",
        workflow_state={"plan": {"action": "analyze", "route": "data_only"}},
    )
    checkpoint = (
        db_session.query(WorkflowCheckpoint)
        .filter_by(execution_attempt_id=old.attempt.id, completed_node="planner_node")
        .one()
    )
    checkpoint.schema_version = "workflow-checkpoint/v999"
    old.attempt.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()

    assert recover_expired_executions(db_session) == [task.id]
    replacement = claim_execution(
        db_session, task_id=task.id, celery_task_id="new", worker_id="w2"
    )
    assert replacement is not None
    assert replacement.resume_next_node is None
    assert replacement.resume_state is None
    event = (
        db_session.query(WorkflowEvent)
        .filter_by(
            execution_attempt_id=replacement.attempt.id,
            event_type="checkpoint_resume_rejected",
        )
        .one()
    )
    assert event.details == {"reason": "checkpoint_schema_version_incompatible"}


def test_cancelled_task_rejects_execution_publish(db_session, test_user) -> None:
    task = _task(db_session, test_user.id)
    execution = claim_execution(
        db_session, task_id=task.id, celery_task_id="one", worker_id="w1"
    )
    assert execution is not None
    cancel_task(db_session, task)
    db_session.commit()
    assert not finish_execution(
        db_session,
        attempt=execution.attempt,
        task_status="completed",
        result_summary="must not publish",
        result_data={},
        error_message=None,
    )
    event = (
        db_session.query(WorkflowEvent)
        .filter_by(
            execution_attempt_id=execution.attempt.id,
            event_type="execution_write_rejected",
        )
        .one()
    )
    assert event.error_code == "execution_fence_lost"
    assert event.details == {"operation": "finish_execution"}


def test_cancellation_revokes_active_execution_and_stops_expiry_recovery(
    db_session, test_user
) -> None:
    task = _task(db_session, test_user.id)
    execution = claim_execution(
        db_session, task_id=task.id, celery_task_id="one", worker_id="w1"
    )
    assert execution is not None
    execution.attempt.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    cancel_task(db_session, task)
    db_session.commit()

    db_session.refresh(task)
    db_session.refresh(execution.attempt)
    assert task.status == "cancelled"
    assert task.active_execution_id is None
    assert execution.attempt.status == "cancelled"
    assert recover_expired_executions(db_session) == []
    assert not checkpoint_workflow_state(
        db_session,
        attempt=execution.attempt,
        stage="planning",
        completed_node="planner_node",
        next_node="data_node",
        workflow_state={"must_not": "persist"},
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


def test_retry_claim_preserves_first_task_start_time(db_session, test_user) -> None:
    task = _task(db_session, test_user.id)
    first = claim_execution(
        db_session, task_id=task.id, celery_task_id="first", worker_id="w1"
    )
    assert first is not None
    first_started_at = first.task.started_at
    assert first_started_at is not None

    record = transition_execution(
        db_session,
        attempt=first.attempt,
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

    retry = claim_execution(
        db_session, task_id=task.id, celery_task_id="retry", worker_id="w2"
    )
    assert retry is not None
    assert retry.task.started_at == first_started_at


def test_retryable_planner_failure_restarts_node_and_preserves_trusted_state(
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
        stage="composing_report",
        completed_node="reviewer_node",
        next_node="smart_router_node",
        workflow_state={
            "data_result": {"status": "ready", "evidence": [{"rows": [[1]]}]},
            "knowledge_result": {"status": "ready", "evidences": [{"chunk_id": 3}]},
            "routing_feedback": {"target": "planner", "reason": "validation_failure"},
        },
    )
    assert checkpoint_workflow_state(
        db_session,
        attempt=old.attempt,
        stage="planning",
        completed_node="planner_node",
        next_node="planning_failure_node",
        workflow_state={
            "planner_failure": {
                "code": "planner_model_retryable_error",
                "retryable": True,
            },
            "terminal_result": {"outcome": "failed"},
            "error": "raw gateway detail must not resume",
        },
    )
    assert transition_execution(
        db_session,
        attempt=old.attempt,
        task_status="retrying",
        stage="retrying",
        attempt_status="retrying",
        error_type="RetryableAnalysisTaskError",
        error_message="temporary outage",
        recovery_instruction="retry_same_execution_scope",
        next_node="planner_node",
        retry_error_code="planner_model_retryable_error",
    )
    db_session.commit()

    replacement = claim_execution(
        db_session, task_id=task.id, celery_task_id="new", worker_id="w2"
    )

    assert replacement is not None
    assert replacement.resume_next_node == "planner_node"
    assert replacement.resume_state["routing_feedback"] == {
        "target": "planner",
        "reason": "validation_failure",
    }
    assert "data_result" not in replacement.resume_state
    assert "knowledge_result" not in replacement.resume_state
    assert replacement.resume_state["recovery_decision"]["mode"] == "rerun_downstream"
    assert replacement.resume_state["retry_context"] == {
        "failed_node": "planner_node",
        "error_code": "planner_model_retryable_error",
        "retry_number": 2,
        "recovery_mode": "rerun_downstream",
    }


def test_retryable_sql_failure_restarts_data_and_keeps_planner_state(
    db_session, test_user
) -> None:
    task = _task(db_session, test_user.id)
    old = claim_execution(
        db_session, task_id=task.id, celery_task_id="old", worker_id="w1"
    )
    assert old is not None
    plan = {"action": "analyze", "route": "hybrid"}
    assert checkpoint_workflow_state(
        db_session,
        attempt=old.attempt,
        stage="planning",
        completed_node="planner_semantic_review_node",
        next_node="data_node",
        workflow_state={"plan": plan, "scope_fingerprint": "frozen-scope"},
    )
    assert checkpoint_workflow_state(
        db_session,
        attempt=old.attempt,
        stage="querying_data",
        completed_node="data_node",
        next_node="knowledge_node",
        workflow_state={
            "plan": plan,
            "data_result": {"status": "failed", "error_code": "business_db_execution_failed"},
            "data_outcome": {"status": "retryable_error"},
        },
    )
    assert transition_execution(
        db_session,
        attempt=old.attempt,
        task_status="retrying",
        stage="retrying",
        attempt_status="retrying",
        error_type="ConnectionError",
        error_message="temporary outage",
        recovery_instruction="retry_same_execution_scope",
        next_node="data_node",
        retry_error_code="business_db_execution_failed",
    )
    db_session.commit()

    replacement = claim_execution(
        db_session, task_id=task.id, celery_task_id="new", worker_id="w2"
    )

    assert replacement is not None
    assert replacement.resume_next_node == "data_node"
    assert replacement.resume_state["plan"] == plan
    assert replacement.resume_state["scope_fingerprint"] == "frozen-scope"
    assert "knowledge_result" not in replacement.resume_state
    assert replacement.resume_state["recovery_decision"]["invalidated_state_keys"]
    assert replacement.resume_state["retry_context"] == {
        "failed_node": "data_node",
        "error_code": "business_db_execution_failed",
        "retry_number": 2,
        "recovery_mode": "rerun_downstream",
    }


def test_retryable_rag_failure_restarts_knowledge_and_keeps_data_state(
    db_session, test_user
) -> None:
    task = _task(db_session, test_user.id)
    old = claim_execution(
        db_session, task_id=task.id, celery_task_id="old", worker_id="w1"
    )
    assert old is not None
    data_result = {"status": "ready", "evidence": [{"rows": [[1]]}]}
    assert checkpoint_workflow_state(
        db_session,
        attempt=old.attempt,
        stage="querying_data",
        completed_node="data_node",
        next_node="knowledge_node",
        workflow_state={"plan": {"action": "analyze", "route": "hybrid"}, "data_result": data_result},
    )
    assert checkpoint_workflow_state(
        db_session,
        attempt=old.attempt,
        stage="retrieving_knowledge",
        completed_node="knowledge_node",
        next_node="reviewer_node",
        workflow_state={"knowledge_result": {"status": "failed", "error_code": "knowledge_retrieval_failed"}},
    )
    assert transition_execution(
        db_session,
        attempt=old.attempt,
        task_status="retrying",
        stage="retrying",
        attempt_status="retrying",
        error_type="ConnectionError",
        error_message="temporary outage",
        recovery_instruction="retry_same_execution_scope",
        next_node="knowledge_node",
        retry_error_code="knowledge_retrieval_failed",
    )
    db_session.commit()

    replacement = claim_execution(
        db_session, task_id=task.id, celery_task_id="new", worker_id="w2"
    )

    assert replacement is not None
    assert replacement.resume_next_node == "knowledge_node"
    assert replacement.resume_state["data_result"] == data_result
    assert replacement.resume_state["retry_context"]["failed_node"] == "knowledge_node"
    assert replacement.resume_state["retry_context"]["error_code"] == "knowledge_retrieval_failed"


def test_retryable_reviewer_failure_restarts_reviewer_and_keeps_evidence(
    db_session, test_user
) -> None:
    task = _task(db_session, test_user.id)
    old = claim_execution(
        db_session, task_id=task.id, celery_task_id="old", worker_id="w1"
    )
    assert old is not None
    evidence_state = {
        "plan": {"action": "analyze", "route": "hybrid"},
        "data_result": {"status": "ready", "evidence": [{"rows": [[1]]}]},
        "knowledge_result": {"status": "ready", "evidences": [{"chunk_id": 4}]},
    }
    assert checkpoint_workflow_state(
        db_session,
        attempt=old.attempt,
        stage="retrieving_knowledge",
        completed_node="knowledge_node",
        next_node="reviewer_node",
        workflow_state=evidence_state,
    )
    assert checkpoint_workflow_state(
        db_session,
        attempt=old.attempt,
        stage="composing_report",
        completed_node="reviewer_node",
        next_node="smart_router_node",
        workflow_state={"reviewer_outcome": {"status": "retryable_error"}, "error": "rate limit"},
    )
    assert transition_execution(
        db_session,
        attempt=old.attempt,
        task_status="retrying",
        stage="retrying",
        attempt_status="retrying",
        error_type="ConnectionError",
        error_message="temporary outage",
        recovery_instruction="retry_same_execution_scope",
        next_node="reviewer_node",
        retry_error_code="reviewer_rate_limited",
    )
    db_session.commit()

    replacement = claim_execution(
        db_session, task_id=task.id, celery_task_id="new", worker_id="w2"
    )

    assert replacement is not None
    assert replacement.resume_next_node == "reviewer_node"
    assert replacement.resume_state["data_result"] == evidence_state["data_result"]
    assert replacement.resume_state["knowledge_result"] == evidence_state["knowledge_result"]
    assert replacement.resume_state["retry_context"]["failed_node"] == "reviewer_node"


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


def test_process_retry_without_checkpoint_restarts_recorded_node_without_old_state(
    db_session, test_user
) -> None:
    task = _task(db_session, test_user.id)
    first = claim_execution(
        db_session, task_id=task.id, celery_task_id="first", worker_id="w1"
    )
    assert first is not None
    assert checkpoint_workflow_state(
        db_session,
        attempt=first.attempt,
        stage="planning",
        completed_node="planner_node",
        next_node="planning_failure_node",
        workflow_state={
            "planner_failure": {
                "code": "planner_model_retryable_error",
                "retryable": True,
            }
        },
    )
    assert transition_execution(
        db_session,
        attempt=first.attempt,
        task_status="retrying",
        stage="retrying",
        attempt_status="retrying",
        error_type="RetryableAnalysisTaskError",
        error_message="temporary outage",
        recovery_instruction="retry_same_execution_scope",
        next_node="planner_node",
    )
    db_session.commit()

    second = claim_execution(
        db_session, task_id=task.id, celery_task_id="second", worker_id="w2"
    )
    assert second is not None
    assert transition_execution(
        db_session,
        attempt=second.attempt,
        task_status="retrying",
        stage="retrying",
        attempt_status="retrying",
        error_type="ConnectionError",
        error_message="transport failure before a node checkpoint",
        recovery_instruction="retry_same_execution_scope",
        next_node="planner_node",
    )
    db_session.commit()

    third = claim_execution(
        db_session, task_id=task.id, celery_task_id="third", worker_id="w3"
    )

    assert third is not None
    assert third.resume_next_node == "planner_node"
    assert third.resume_state["retry_context"] == {
        "failed_node": "planner_node",
        "error_code": "ConnectionError",
        "retry_number": 3,
        "recovery_mode": "rerun_downstream",
    }
