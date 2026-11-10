"""K4: a task runs on the business configuration it was created with."""

import copy
import json
from pathlib import Path

import pytest
from app.core.config import snapshot as config_snapshot
from app.core.config.snapshot import (
    SNAPSHOT_FIELDS,
    build_config_snapshot,
    config_snapshot_hash,
    runtime_settings,
    task_config_scope,
)
from app.core.settings import get_settings
from app.modules.runtime import context_budget


def test_snapshot_holds_business_domains_and_no_secrets():
    snapshot = build_config_snapshot()

    assert snapshot["version"] == 1
    assert set(snapshot["values"]) == SNAPSHOT_FIELDS
    assert "rag_retrieval_top_k" in SNAPSHOT_FIELDS
    assert "model_tool_mode" in SNAPSHOT_FIELDS
    for name in SNAPSHOT_FIELDS:
        assert not any(
            word in name for word in ("password", "secret", "key", "token_")
        ), name
        assert "url" not in name, name
    json.dumps(snapshot)  # stored as JSONB


def test_hash_is_stable_and_changes_with_any_value():
    snapshot = build_config_snapshot()
    same = json.loads(json.dumps(snapshot))
    changed = copy.deepcopy(snapshot)
    changed["values"]["rag_retrieval_top_k"] += 1

    assert config_snapshot_hash(snapshot) == config_snapshot_hash(same)
    assert len(config_snapshot_hash(snapshot)) == 64
    assert config_snapshot_hash(changed) != config_snapshot_hash(snapshot)


def test_running_task_ignores_a_config_change_made_after_creation(monkeypatch):
    snapshot = build_config_snapshot()
    created_with = snapshot["values"]["context_max_rows_when_compressed"]
    monkeypatch.setattr(
        get_settings(), "context_max_rows_when_compressed", created_with + 5
    )

    with task_config_scope(snapshot):
        assert runtime_settings().context_max_rows_when_compressed == created_with
        assert context_budget.runtime_settings is runtime_settings
    assert runtime_settings().context_max_rows_when_compressed == created_with + 5


def test_recovered_attempt_reads_the_same_values_from_stored_json():
    snapshot = build_config_snapshot()
    snapshot["values"]["rag_rerank_top_k"] = 2
    stored = json.loads(json.dumps(snapshot))  # what a later attempt reads back

    with task_config_scope(snapshot):
        first = runtime_settings().model_dump(include=set(SNAPSHOT_FIELDS))
    with task_config_scope(stored):
        recovered = runtime_settings().model_dump(include=set(SNAPSHOT_FIELDS))

    assert first == recovered
    assert recovered["rag_rerank_top_k"] == 2


def test_infrastructure_settings_still_come_from_get_settings():
    snapshot = build_config_snapshot()

    with task_config_scope(snapshot):
        task_settings = runtime_settings()

    assert task_settings.database_host == get_settings().database_host
    assert task_settings.database_password == get_settings().database_password


def test_task_without_snapshot_uses_current_settings():
    with task_config_scope(None):
        assert runtime_settings() is get_settings()


def test_snapshot_values_are_validated():
    snapshot = build_config_snapshot()
    snapshot["values"]["review_qualification_mode"] = "not-a-mode"

    with pytest.raises(ValueError), task_config_scope(snapshot):
        pass


def test_unknown_snapshot_version_is_refused():
    with (
        pytest.raises(ValueError, match="version"),
        task_config_scope({"version": 99, "values": {}}),
    ):
        pass


def test_business_reads_in_nodes_go_through_runtime_settings():
    """The K4 reads must not drift back to get_settings()."""
    backend = Path(config_snapshot.__file__).resolve().parents[3]
    for relative in (
        "app/modules/knowledge/tool.py",
        "app/modules/knowledge/tool_agent.py",
        "app/modules/knowledge/rag/retrieval.py",
        "app/modules/memory/service.py",
        "app/modules/reporting/semantic_review_service.py",
        "app/modules/runtime/context_budget.py",
        "app/modules/runtime/tool_loop.py",
        "app/modules/workflow/orchestration/nodes.py",
    ):
        source = (backend / relative).read_text(encoding="utf-8")
        for name in SNAPSHOT_FIELDS:
            assert f"get_settings().{name}" not in source, (relative, name)
