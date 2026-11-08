from types import SimpleNamespace

from app.modules.workflow import tasks


def _record_shadow(monkeypatch, plan):
    events = []
    monkeypatch.setattr(
        tasks, "append_workflow_event", lambda db, **event: events.append(event)
    )
    record = SimpleNamespace(question="那华北呢？", company_id=1)
    tasks._record_plan_rules(None, record, SimpleNamespace(attempt=None), plan)
    return events[0]["details"]


def test_shadow_reads_the_resolved_question_of_a_follow_up(monkeypatch):
    plan = {
        "action": "analyze",
        "route": "data_only",
        "resolved_question": "华北区销售额是多少？",
    }

    details = _record_shadow(monkeypatch, plan)

    assert details["question_source"] == "resolved"
    assert [hit["rule"] for hit in details["hits"]] == ["R4"]
    assert "华北" not in str(details)


def test_shadow_falls_back_to_the_original_question(monkeypatch):
    details = _record_shadow(monkeypatch, {"action": "analyze", "route": "hybrid"})

    assert details["question_source"] == "original"
    assert details["hits"] == []
