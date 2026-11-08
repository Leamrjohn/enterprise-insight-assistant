import pytest
from app.modules.workflow.audit.events_models import WorkflowEvent
from app.modules.workflow.audit.model_call import ModelCallRecord
from app.modules.workflow.lifecycle.execution import (
    claim_execution,
    transition_execution,
)
from app.modules.workflow.lifecycle.versioning import (
    STABLE_WORKFLOW_VERSION,
    WorkflowRollbackError,
    rollback_task_workflow_version,
    workflow_policy_snapshot,
)
from app.modules.workflow.models import AnalysisTask


def _candidate_task(db, user_id: int) -> AnalysisTask:
    task = AnalysisTask(
        user_id=user_id,
        question="candidate release test",
        status="queued",
        stage="queued",
        workflow_policy_snapshot=workflow_policy_snapshot("v2-candidate"),
    )
    db.add(task)
    db.commit()
    return task


def test_retry_rollback_preserves_candidate_attempt_and_call_ledger(
    db_session, test_user
) -> None:
    task = _candidate_task(db_session, test_user.id)
    candidate = claim_execution(
        db_session, task_id=task.id, celery_task_id="candidate", worker_id="w1"
    )
    assert candidate is not None
    assert candidate.attempt.workflow_version == "v2-candidate"
    ledger_entry = ModelCallRecord(
        task_id=task.id,
        execution_attempt_id=candidate.attempt.id,
        node_name="planner",
        provider="test",
        model_name="candidate-model",
        result_category="retryable_error",
        billing_status="unknown",
    )
    db_session.add(ledger_entry)
    assert transition_execution(
        db_session,
        attempt=candidate.attempt,
        task_status="retrying",
        stage="retrying",
        attempt_status="retrying",
        error_type="CandidateRegression",
        error_message="candidate failed the frozen case",
        recovery_instruction="retry_same_execution_scope",
        next_node="planner_node",
    )
    db_session.commit()

    rolled_back = rollback_task_workflow_version(db_session, task_id=task.id)

    assert rolled_back.workflow_policy_snapshot == workflow_policy_snapshot(
        "v2-candidate"
    )
    assert rolled_back.workflow_version_override == STABLE_WORKFLOW_VERSION
    assert db_session.get(ModelCallRecord, ledger_entry.id) is not None
    event = (
        db_session.query(WorkflowEvent)
        .filter(WorkflowEvent.execution_attempt_id == candidate.attempt.id)
        .order_by(WorkflowEvent.sequence.desc())
        .first()
    )
    assert event is not None
    assert event.event_type == "workflow_version_rolled_back"
    assert event.details == {"from_version": "v2-candidate", "to_version": "v1"}

    replacement = claim_execution(
        db_session, task_id=task.id, celery_task_id="stable", worker_id="w2"
    )
    assert replacement is not None
    assert replacement.attempt.workflow_version == STABLE_WORKFLOW_VERSION
    assert candidate.attempt.workflow_version == "v2-candidate"
    assert (
        db_session.query(ModelCallRecord)
        .filter(ModelCallRecord.execution_attempt_id == candidate.attempt.id)
        .count()
        == 1
    )


def test_running_or_unknown_release_cannot_be_rolled_back(
    db_session, test_user
) -> None:
    task = _candidate_task(db_session, test_user.id)
    with pytest.raises(WorkflowRollbackError, match="auditable prior attempt"):
        rollback_task_workflow_version(db_session, task_id=task.id)

    candidate = claim_execution(
        db_session, task_id=task.id, celery_task_id="candidate", worker_id="w1"
    )
    assert candidate is not None
    with pytest.raises(WorkflowRollbackError, match="queued or retrying"):
        rollback_task_workflow_version(db_session, task_id=task.id)
    with pytest.raises(WorkflowRollbackError, match="not a supported release"):
        rollback_task_workflow_version(
            db_session, task_id=task.id, target_version="not-a-release"
        )
