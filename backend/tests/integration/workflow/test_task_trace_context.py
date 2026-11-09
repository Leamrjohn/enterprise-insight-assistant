"""O1: a task stores the traceparent of the request that created it."""

from app.core import tracing
from app.modules.workflow.repository import create_task


def test_task_stores_the_creating_request_traceparent(db_session, test_user):
    with tracing.span("http.request") as current:
        task = create_task(db_session, user_id=test_user.id, question="trace me")
    db_session.flush()
    db_session.refresh(task)

    trace_id = format(current.get_span_context().trace_id, "032x")
    assert task.trace_context is not None
    assert task.trace_context.split("-")[1] == trace_id
    assert "trace me" not in task.trace_context


def test_task_outside_a_request_starts_without_a_parent(db_session, test_user):
    task = create_task(db_session, user_id=test_user.id, question="no request")

    assert task.trace_context is None
