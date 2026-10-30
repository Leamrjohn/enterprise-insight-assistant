from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from scripts.evaluation import prepare_business_evaluation as prepare
from scripts.evaluation import run_smoke_tests as smoke


def saved_round(identity):
    return [
        {"event": "identity", "value": identity},
        *[{"event": "result", "round": 1, "case_id": cid} for cid in smoke.IDS],
        {"event": "round", "round": 1},
        {"event": "done"},
    ]


def test_resume_requires_matching_identity_and_complete_unique_cases():
    identity = {"git": "revision-a", "fixtures": "hash-a"}
    assert smoke.resume_round(saved_round(identity), identity) == 2
    with pytest.raises(ValueError):
        smoke.resume_round(saved_round(identity), {**identity, "git": "revision-b"})
    with pytest.raises(ValueError):
        smoke.resume_round(saved_round(identity)[1:], identity)
    duplicate = saved_round(identity)
    duplicate[2] = duplicate[1].copy()
    with pytest.raises(ValueError):
        smoke.resume_round(duplicate, identity)
    with pytest.raises(ValueError):
        smoke.resume_round(saved_round(identity)[:-1], identity)


def test_run_names_are_independent_and_resume_is_explicit():
    first = smoke.parse_run_args([])
    second = smoke.parse_run_args([])
    assert first.run_id != second.run_id
    assert not first.resume
    resumed = smoke.parse_run_args(["--resume", "--run-id", first.run_id])
    assert resumed.resume and resumed.run_id == first.run_id


@pytest.mark.parametrize("field", ["model", "business_dump_sha256"])
def test_resume_rejects_changed_runtime(field):
    identity = {"runtime": {"model": "model-a", "business_dump_sha256": "data-a"}}
    changed = {"runtime": {**identity["runtime"], field: "changed"}}
    with pytest.raises(ValueError, match="changed run identity"):
        smoke.resume_round(saved_round(identity), changed)


@pytest.mark.parametrize(
    "args",
    [["--resume"], ["--run-id", "../old"], ["--run-id", "C:\\old"], ["--run-id", ""]],
)
def test_run_name_rejects_missing_or_unsafe_paths(args):
    with pytest.raises(SystemExit):
        smoke.parse_run_args(args)


@pytest.fixture
def smoke_runtime(monkeypatch):
    import httpx
    from app.core import security
    from app.db import session
    from app.modules.evaluation import business, business_schemas, observation

    events, submissions = [], []
    monkeypatch.setattr(
        smoke,
        "emit",
        lambda event, **fields: events.append(dict(event=event, **fields)),
    )
    monkeypatch.setattr(security, "hash_password", lambda _: "test-hash")
    monkeypatch.setattr(session, "SessionLocal", lambda: nullcontext(MagicMock()))
    monkeypatch.setattr(session, "set_tenant_scope", lambda *_: None)
    monkeypatch.setattr(
        prepare,
        "_bootstrap_tenant",
        lambda _: ({"user_id": 1, "company_id": 1}, "unused"),
    )
    monkeypatch.setattr(
        prepare, "_create_source_snapshot", lambda *_: {"data_source_id": 1}
    )
    monkeypatch.setattr(
        business_schemas.EvaluationCase,
        "model_validate",
        lambda data: SimpleNamespace(**data),
    )
    monkeypatch.setattr(
        observation, "observation_from_persisted_task", lambda *_, **__: object()
    )
    monkeypatch.setattr(
        business,
        "evaluate_case",
        lambda *_: SimpleNamespace(passed=True, violations=[]),
    )
    client = SimpleNamespace(headers={}, timeout=None)
    monkeypatch.setattr(httpx, "Client", lambda **_: nullcontext(client))

    def request(_client, method, path, **kwargs):
        if path == "auth/login":
            return {"access_token": "test-token"}
        if path == "conversations":
            return {"id": 1}
        if method == "POST" and path.endswith("/messages"):
            submissions.append(kwargs["payload"]["content"])
            return {"task_id": len(submissions)}
        if method == "GET" and "/tasks/" in path:
            return {
                "id": len(submissions),
                "status": "completed",
                "stage": "completed",
                "observability": {"model_usage": {"tokens": 1, "cost": 0}},
            }
        raise AssertionError(f"Unexpected request: {method} {path}")

    monkeypatch.setattr(prepare, "_request_json", request)
    payload = {
        "documents": {},
        "selected": [
            {
                "case": {
                    "case_id": cid,
                    "question": cid,
                    "document_scope": [],
                    "max_tokens": 100,
                }
            }
            for cid in smoke.IDS
        ],
    }
    return payload, events, submissions, client


@pytest.mark.parametrize("start_round", [None, 2, 3])
def test_one_invocation_submits_only_one_round(smoke_runtime, start_round):
    payload, events, submissions, _ = smoke_runtime
    if start_round is not None:
        payload["start_round"] = start_round
    smoke.run_container(payload)
    assert submissions == list(smoke.IDS)
    assert [event["round"] for event in events if event["event"] == "round"] == [
        start_round or 1
    ]
    assert events[-1] == {"event": "done"}


def test_pending_review_stops_without_waiting_cancelling_or_submitting_more(
    monkeypatch, smoke_runtime
):
    from app.modules.evaluation import observation

    payload, events, submissions, client = smoke_runtime
    original = prepare._request_json
    terminal_observation = MagicMock(
        side_effect=ValueError("task is not in an evaluable terminal state")
    )
    monkeypatch.setattr(
        observation, "observation_from_persisted_task", terminal_observation
    )

    def request(*args, **kwargs):
        result = original(*args, **kwargs)
        if args[1] == "GET" and "/tasks/" in args[2]:
            result.update(status="awaiting_review", stage="awaiting_review")
        return result

    monkeypatch.setattr(prepare, "_request_json", request)
    sleep = MagicMock(side_effect=AssertionError("must not wait for human review"))
    monkeypatch.setattr(smoke.time, "sleep", sleep)
    client.post = MagicMock()
    smoke.run_container(payload)
    assert submissions == [smoke.IDS[0]]
    sleep.assert_not_called()
    client.post.assert_not_called()
    terminal_observation.assert_not_called()
    result = next(e for e in events if e["event"] == "result")
    assert result["status"] == "awaiting_review"
    assert result["category"] == "失败"
    assert events[-1] == {"event": "stop", "reason": "human_review_required"}
