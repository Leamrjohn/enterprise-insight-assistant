from types import SimpleNamespace

from app.models.analysis_task import AnalysisTask
from app.services.outbox_service import (
    create_analysis_task_event,
    pending_event_ids,
    publish_analysis_task_event,
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
    assert event.status == "published"
    assert event.publish_attempt_count == 2
    assert event.last_error is None
    assert task.celery_task_id == "celery-test-id"
    assert pending_event_ids(db_session) == []
