"""K4: a task stores the business configuration it was created with."""

from app.core.config.snapshot import (
    build_config_snapshot,
    config_snapshot_hash,
    runtime_settings,
    task_config_scope,
)
from app.core.settings import get_settings
from app.modules.workflow.models import AnalysisTask
from app.modules.workflow.repository import create_task


def test_task_stores_its_config_snapshot_and_hash(db_session, test_user):
    task = create_task(db_session, user_id=test_user.id, question="snapshot me")
    db_session.flush()
    db_session.expire_all()
    stored = db_session.get(AnalysisTask, task.id)

    assert stored is not None
    assert stored.config_snapshot == build_config_snapshot()
    assert stored.config_snapshot_hash == config_snapshot_hash(stored.config_snapshot)


def test_tasks_with_the_same_config_share_a_hash(db_session, test_user):
    first = create_task(db_session, user_id=test_user.id, question="one")
    second = create_task(db_session, user_id=test_user.id, question="two")

    assert first.config_snapshot_hash == second.config_snapshot_hash


def test_stored_snapshot_wins_over_a_later_config_change(
    db_session, test_user, monkeypatch
):
    task = create_task(db_session, user_id=test_user.id, question="frozen")
    db_session.flush()
    created_with = task.config_snapshot["values"]["rag_retrieval_top_k"]
    monkeypatch.setattr(get_settings(), "rag_retrieval_top_k", created_with + 3)
    db_session.expire_all()
    reloaded = db_session.get(AnalysisTask, task.id)

    assert reloaded is not None
    with task_config_scope(reloaded.config_snapshot):
        assert runtime_settings().rag_retrieval_top_k == created_with


def test_operator_command_reports_what_differs_from_current(
    db_session, test_user, monkeypatch
):
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[3] / "scripts/db/show_task_config.py"
    spec = importlib.util.spec_from_file_location("show_task_config", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    task = create_task(db_session, user_id=test_user.id, question="describe me")
    created_with = task.config_snapshot["values"]["memory_ttl_days"]
    assert module.describe(task)["differs_from_current"] == {}

    monkeypatch.setattr(get_settings(), "memory_ttl_days", created_with + 1)
    report = module.describe(task, show_all=True)

    assert report["hash_matches_values"] is True
    assert report["differs_from_current"] == {
        "memory_ttl_days": {"task": created_with, "current": created_with + 1}
    }
    assert report["values"]["memory_ttl_days"] == created_with
