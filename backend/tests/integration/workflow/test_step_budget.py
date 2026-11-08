"""Stage 3.4: a workflow that keeps looping must stop at the step budget and fail."""

import pytest
from app.db.session import SessionLocal
from app.modules.identity.models import User
from app.modules.workflow import tasks as analysis_tasks
from app.modules.workflow.models import AnalysisTask
from app.modules.workflow.orchestration import graph as graph_module
from app.modules.workflow.tasks import process_analysis_task
from langgraph.errors import GraphRecursionError
from tests.integration.workflow.test_tasks import (
    _delete_created_records,
    create_conversation_analysis_task,
)


def test_router_loop_is_cut_off_by_the_graph_step_budget(monkeypatch) -> None:
    visits: list[str] = []

    def node(name: str):
        def run(state):
            visits.append(name)
            return {}

        return run

    for name in (
        "planner_node",
        "planner_semantic_review_node",
        "reviewer_node",
        "smart_router_node",
    ):
        monkeypatch.setattr(graph_module, name, node(name))
    monkeypatch.setattr(graph_module, "_route_from_start", lambda state: "planner_node")
    monkeypatch.setattr(
        graph_module, "_route_after_planner", lambda state: "reviewer_node"
    )
    # A router bug that never ends: the step budget is the last line of defence.
    monkeypatch.setattr(
        graph_module, "_route_after_smart_router", lambda state: "reviewer_node"
    )

    with pytest.raises(GraphRecursionError):
        graph_module.build_workflow().compile().invoke(
            {}, {"recursion_limit": graph_module.MAX_GRAPH_STEPS}
        )
    assert len(visits) <= graph_module.MAX_GRAPH_STEPS


def test_worker_fails_without_retry_when_step_budget_is_exhausted(
    monkeypatch,
) -> None:
    db = SessionLocal()
    task_id = user_id = None
    try:
        user = User(name="step-budget-user", api_key="step-budget-key")
        db.add(user)
        db.flush()
        task, _ = create_conversation_analysis_task(db, user.id, question="loop")
        db.commit()
        task_id, user_id = task.id, user.id

        def exhausted(*args, **kwargs):
            raise GraphRecursionError("Recursion limit of 20 reached")

        monkeypatch.setattr(analysis_tasks, "run_analysis", exhausted)
        retry_calls: list[object] = []
        monkeypatch.setattr(
            process_analysis_task, "retry", lambda *a, **k: retry_calls.append(k)
        )

        with pytest.raises(GraphRecursionError):
            process_analysis_task.run(task_id=task_id)

        db.expire_all()
        stored = db.get(AnalysisTask, task_id)
        assert stored is not None
        assert stored.status == "failed"
        assert retry_calls == []
    finally:
        _delete_created_records(db, task_id, user_id)
