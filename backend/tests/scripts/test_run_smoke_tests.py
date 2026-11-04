import json
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from app.modules.evaluation.business_schemas import EvaluationFixture
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


@pytest.mark.parametrize("review_task_id", [1, 7])
def test_pending_review_continues_without_waiting_cancelling_or_approving(
    monkeypatch, smoke_runtime, review_task_id
):
    from app.modules.evaluation import observation

    payload, events, submissions, client = smoke_runtime
    original = prepare._request_json

    def observe(*args, task_id, **kwargs):
        if task_id == review_task_id:
            raise ValueError("task is not in an evaluable terminal state")
        return object()

    terminal_observation = MagicMock(side_effect=observe)
    monkeypatch.setattr(
        observation, "observation_from_persisted_task", terminal_observation
    )

    def request(*args, **kwargs):
        result = original(*args, **kwargs)
        if args[1] == "GET" and args[2].endswith(f"/tasks/{review_task_id}"):
            result.update(status="awaiting_review", stage="awaiting_review")
        return result

    monkeypatch.setattr(prepare, "_request_json", request)
    sleep = MagicMock(side_effect=AssertionError("must not wait for human review"))
    monkeypatch.setattr(smoke.time, "sleep", sleep)
    client.post = MagicMock()
    smoke.run_container(payload)
    assert submissions == list(smoke.IDS)
    sleep.assert_not_called()
    client.post.assert_not_called()
    assert terminal_observation.call_count == len(smoke.IDS) - 1
    assert all(
        call.kwargs["task_id"] != review_task_id
        for call in terminal_observation.call_args_list
    )
    results = [e for e in events if e["event"] == "result"]
    assert len(results) == len(smoke.IDS)
    result = results[review_task_id - 1]
    assert result["status"] == "awaiting_review"
    assert result["category"] == "失败"
    assert result["violations"] == []
    assert all(r["category"] == "成功" for r in results if r is not result)
    assert not any(e["event"] == "stop" for e in events)
    assert events[-1] == {"event": "done"}


@pytest.mark.parametrize(
    "status,passed,category,finishes_round",
    [
        ("partial", False, "结果错误", True),
        ("completed", False, "结果错误", True),
        ("failed", False, "失败", False),
        ("cancelled", False, "失败", False),
        ("partial", True, "成功", True),
        ("needs_clarification", True, "成功", True),
    ],
)
def test_only_failures_stop_the_round_before_next_submission(
    monkeypatch, smoke_runtime, status, passed, category, finishes_round
):
    from app.modules.evaluation import business

    payload, events, submissions, client = smoke_runtime
    original = prepare._request_json

    def request(*args, **kwargs):
        result = original(*args, **kwargs)
        if args[1] == "GET" and args[2].endswith("/tasks/1"):
            result.update(status=status)
        return result

    monkeypatch.setattr(prepare, "_request_json", request)
    monkeypatch.setattr(
        business,
        "evaluate_case",
        lambda *_: SimpleNamespace(
            passed=passed, violations=[] if passed else ["outcome_correct"]
        ),
    )
    client.post = MagicMock()
    smoke.run_container(payload)
    results = [e for e in events if e["event"] == "result"]
    assert results[0]["category"] == category
    if category == "结果错误":
        assert results[0]["violations"] == ["outcome_correct"]
    assert submissions == (list(smoke.IDS) if finishes_round else [smoke.IDS[0]])
    client.post.assert_not_called()
    if finishes_round:
        assert events[-1] == {"event": "done"}
    else:
        assert len(results) == 1
        assert events[-1] == {"event": "stop", "reason": "unexpected_result"}
        assert not any(e["event"] in {"round", "done"} for e in events)


@pytest.mark.parametrize(
    "rc,events,expected",
    [
        (0, [{"event": "result", "category": "成功"}, {"event": "done"}], 0),
        (0, [{"event": "result", "category": "结果错误"}, {"event": "done"}], 1),
        (0, [{"event": "stop", "reason": "unexpected_result"}], 1),
        (1, [{"event": "done"}], 1),
        (0, [], 1),
    ],
)
def test_a_finished_round_with_wrong_results_still_exits_nonzero(rc, events, expected):
    assert smoke.exit_code(rc, events) == expected


def test_timeout_cancels_and_stops_before_next_submission(monkeypatch, smoke_runtime):
    payload, events, submissions, client = smoke_runtime
    original = prepare._request_json
    clock = [0]
    monkeypatch.setattr(smoke.time, "monotonic", lambda: clock[0])

    def request(*args, **kwargs):
        result = original(*args, **kwargs)
        if args[1] == "GET" and "/tasks/" in args[2]:
            result.update(status="running")
            clock[0] = 181
        return result

    monkeypatch.setattr(prepare, "_request_json", request)
    client.post = MagicMock(return_value=SimpleNamespace(status_code=200))
    smoke.run_container(payload)
    assert submissions == [smoke.IDS[0]]
    client.post.assert_called_once_with("conversations/1/tasks/1/cancel")
    results = [e for e in events if e["event"] == "result"]
    assert len(results) == 1 and results[0]["category"] == "无响应"
    assert events[-1] == {"event": "stop", "reason": "unexpected_result"}


def test_long_document_cases_are_valid_and_their_files_are_in_the_corpus():
    root = Path(__file__).resolve().parents[3]
    fixture = EvaluationFixture.model_validate_json(
        (
            root
            / "backend/tests/fixtures/evaluation"
            / smoke.LONG_DOCUMENT_SELECTION["file"]
        ).read_bytes()
    )
    manifest = json.loads(
        (root / "data/business_knowledge_base/manifest.json").read_text(
            encoding="utf-8"
        )
    )
    corpus = {artifact["path"] for artifact in manifest["artifacts"]}

    assert tuple(case.case_id for case in fixture.cases) == smoke.LONG_DOCUMENT_IDS
    for case in fixture.cases:
        assert case.document_scope and set(case.document_scope) <= corpus


def test_wrong_long_document_answer_does_not_stop_the_round(monkeypatch, smoke_runtime):
    from app.modules.evaluation import business

    payload, events, submissions, _client = smoke_runtime
    monkeypatch.setattr(
        business,
        "evaluate_case",
        lambda case, *_: SimpleNamespace(
            passed=case.case_id != smoke.LONG_DOCUMENT_IDS[0],
            violations=[],
        ),
    )

    smoke.run_container(payload)

    assert submissions == list(smoke.IDS)
    assert events[-1] == {"event": "done"}
