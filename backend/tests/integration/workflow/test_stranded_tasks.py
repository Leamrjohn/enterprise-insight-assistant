from datetime import timedelta
from uuid import uuid4

from app.db.clock import database_now
from app.modules.conversations.models import Conversation, ConversationMessage
from app.modules.workflow import outbox_tasks, tasks
from app.modules.workflow.lifecycle.execution import (
    settle_stranded_task,
    stranded_retrying_task_ids,
)
from app.modules.workflow.lifecycle.execution_attempt import TaskExecutionAttempt
from app.modules.workflow.models import AnalysisTask


def test_only_unheld_old_retrying_tasks_are_stranded(db_session, test_user):
    def task(status, stage, active_execution_id=None):
        row = AnalysisTask(
            user_id=test_user.id,
            question="销售额",
            status=status,
            stage=stage,
            active_execution_id=active_execution_id,
        )
        db_session.add(row)
        db_session.flush()
        return row.id

    lost = task("retrying", "retrying")
    running = task("running", "planning", active_execution_id=str(uuid4()))
    queued = task("queued", "queued")
    ours = {lost, running, queued}
    now = database_now(db_session)

    def stranded(at):
        found = stranded_retrying_task_ids(
            db_session, older_than=timedelta(minutes=2), now=at, limit=10_000
        )
        return set(found) & ours

    three_minutes_later = stranded(now + timedelta(minutes=3))
    right_away = stranded(now)

    assert three_minutes_later == {lost}
    assert right_away == set()


def _stranded_task(
    db_session, test_user, status="retrying", stage="retrying", **fields
):
    task = AnalysisTask(
        user_id=test_user.id,
        question="销售额",
        status=status,
        stage=stage,
        **fields,
    )
    db_session.add(task)
    db_session.flush()
    db_session.add(
        TaskExecutionAttempt(
            task_id=task.id,
            execution_id=str(uuid4()),
            status="expired",
            lease_expires_at=database_now(db_session),
        )
    )
    db_session.flush()
    return task


def _settle(db_session, task, at=None):
    return settle_stranded_task(
        db_session,
        task_id=task.id,
        max_redeliveries=3,
        max_stranded=timedelta(minutes=30),
        now=at,
    )


def test_redelivers_three_times_then_dead_letters(db_session, test_user):
    task = _stranded_task(db_session, test_user)

    outcomes = [_settle(db_session, task) for _ in range(4)]

    assert outcomes == ["redeliver", "redeliver", "redeliver", "exhausted"]
    db_session.refresh(task)
    assert (task.status, task.error_type) == ("failed", "DeliveryExhausted")


def test_dead_letters_once_stranded_too_long(db_session, test_user):
    task = _stranded_task(db_session, test_user)
    later = database_now(db_session) + timedelta(minutes=31)

    assert _settle(db_session, task, at=later) == "exhausted"


def test_claimed_task_is_never_dead_lettered(db_session, test_user):
    task = _stranded_task(db_session, test_user, status="running", stage="planning")

    assert _settle(db_session, task) == "claimed"
    db_session.refresh(task)
    assert task.status == "running"


class _KeepOpen:
    """Hand the rolled-back test session to the Beat task without letting it close."""

    def __init__(self, session):
        self._session = session

    def __getattr__(self, name):
        return getattr(self._session, name)

    def close(self):
        pass


def test_dead_letter_tells_the_user_the_task_failed(db_session, test_user, monkeypatch):
    conversation = Conversation(user_id=test_user.id, title="经营问答")
    db_session.add(conversation)
    db_session.flush()
    task = _stranded_task(db_session, test_user, conversation_id=conversation.id)
    message = ConversationMessage(
        conversation_id=conversation.id,
        role="assistant",
        status="running",
        content=tasks.RETRYING_WORKER_MESSAGE,
        analysis_task_id=task.id,
    )
    db_session.add(message)
    db_session.flush()
    delivered = []
    monkeypatch.setattr(outbox_tasks, "SessionLocal", lambda: _KeepOpen(db_session))
    monkeypatch.setattr(
        outbox_tasks, "stranded_retrying_task_ids", lambda db, **_: [task.id]
    )
    # Zero allowed redeliveries: the first reconcile pass dead-letters the task.
    monkeypatch.setattr(outbox_tasks, "MAX_STRANDED_REDELIVERIES", 0)
    monkeypatch.setattr(
        tasks.process_analysis_task,
        "delay",
        lambda *, task_id: delivered.append(task_id),
    )

    result = outbox_tasks.reconcile_stranded_analysis_tasks()
    db_session.refresh(message)

    assert result == {"stranded": 1, "exhausted": 1, "delivered": 0}
    assert delivered == []
    assert message.status == "failed"
    assert message.content == tasks.GENERIC_WORKER_FAILURE_MESSAGE
