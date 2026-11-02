"""The evidence review's memory flags reach the memory, and only when they should."""

import json

from app.core.gateway.base import ModelGateway
from app.modules.reporting.semantic_review_service import SemanticReviewService
from app.modules.workflow.orchestration import nodes
from scripts.evaluation.run_memory_flag_evaluation import FIXTURE, summarize

REVIEW = json.dumps(
    {
        "verdict": "supported",
        "reason": "ok",
        "contradicted_memories": [{"memory_id": 7, "reason": "数字不同"}],
    }
)


class _Gateway(ModelGateway):
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def chat(self, prompt, system_prompt=None, *, json_mode=False):
        self.calls.append({"prompt": prompt, "system_prompt": system_prompt})
        return REVIEW

    def count_tokens(self, text):  # pragma: no cover - not used here
        return len(text)


def _review(gateway, memories=None):
    return SemanticReviewService(gateway=gateway).review_evidence(
        question="q",
        plan={},
        data_result={},
        knowledge_result={},
        report={},
        memories_used=memories,
    )


def test_review_prompt_is_unchanged_without_memories():
    gateway = _Gateway()
    _review(gateway)
    assert "memories_used" not in gateway.calls[0]["system_prompt"]
    assert "memories_used" not in gateway.calls[0]["prompt"]


def test_review_sees_used_memories_and_returns_its_flags():
    gateway = _Gateway()
    review = _review(gateway, [{"memory_id": 7, "content": {}}])
    assert "memories_used" in gateway.calls[0]["system_prompt"]
    assert json.loads(gateway.calls[0]["prompt"])["memories_used"][0]["memory_id"] == 7
    assert review.contradicted_memories[0].memory_id == 7


class _FakeSession:
    committed = False
    rolled_back = False

    def commit(self):
        type(self).committed = True

    def rollback(self):
        type(self).rolled_back = True

    def close(self):
        pass


def _state():
    return {"company_id": 3, "planner_memory": [{"memory_id": 7}]}


def _result(flags):
    return {"semantic_review": {"contradicted_memories": flags}}


def test_node_passes_only_the_used_memories_as_allowed(monkeypatch):
    seen = {}
    monkeypatch.setattr(nodes, "SessionLocal", _FakeSession)
    monkeypatch.setattr(nodes, "set_tenant_scope", lambda *_: None)
    monkeypatch.setattr(
        "app.modules.memory.service.flag_memories_from_model",
        lambda _db, **kwargs: seen.update(kwargs),
    )
    nodes._flag_contradicted_memories(_state(), _result([{"memory_id": 7}]))
    assert seen["allowed_ids"] == {7}
    assert seen["company_id"] == 3


def test_no_flags_opens_no_session(monkeypatch):
    def fail():
        raise AssertionError("no session should be opened")

    monkeypatch.setattr(nodes, "SessionLocal", fail)
    nodes._flag_contradicted_memories(_state(), _result([]))
    nodes._flag_contradicted_memories(_state(), {})


def test_a_flagging_failure_does_not_cost_the_report(monkeypatch):
    monkeypatch.setattr(nodes, "SessionLocal", _FakeSession)
    monkeypatch.setattr(nodes, "set_tenant_scope", lambda *_: None)

    def boom(_db, **_kwargs):
        raise RuntimeError("database down")

    monkeypatch.setattr("app.modules.memory.service.flag_memories_from_model", boom)
    nodes._flag_contradicted_memories(_state(), _result([{"memory_id": 7}]))
    assert _FakeSession.rolled_back


def test_flag_summary_treats_any_false_flag_as_a_miss_of_the_target():
    rows = [
        {"case_id": "a", "should_flag": True, "flagged": True},
        {"case_id": "b", "should_flag": False, "flagged": True},
    ]
    summary = summarize(rows)
    assert summary["flag_recall"] == 1.0
    assert summary["false_flags"] == ["b"]
    assert not summary["meets_target"]


def test_flag_fixture_has_both_labels_in_both_splits():
    cases = json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]
    for split in ("development", "heldout"):
        assert {c["should_flag"] for c in cases if c["split"] == split} == {True, False}
