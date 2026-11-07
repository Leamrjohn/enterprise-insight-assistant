from decimal import Decimal
from types import SimpleNamespace

import pytest
from app.core.gateway.base import ModelGateway
from scripts.evaluation.run_planner_route_evaluation import (
    BudgetGuardExceeded,
    BudgetGuardGateway,
    evaluate,
    load_label_cases,
    load_route_cases,
)


class _Echo(ModelGateway):
    def __init__(self) -> None:
        self.calls = 0

    def chat(self, prompt, system_prompt=None, *, json_mode=False) -> str:
        self.calls += 1
        return "{}"

    def count_tokens(self, text: str) -> int:
        return 1000


def test_guard_refuses_the_call_that_would_cross_the_call_ceiling() -> None:
    inner = _Echo()
    guard = BudgetGuardGateway(inner, max_calls=2, max_cost=Decimal(1))
    guard.chat("a")
    guard.chat("b")
    with pytest.raises(BudgetGuardExceeded):
        guard.chat("c")
    assert inner.calls == 2


def test_guard_refuses_before_spending_when_worst_case_exceeds_cost_ceiling() -> None:
    inner = _Echo()
    # One call worst case: 1000 prompt + 512 completion tokens ~= $0.000914.
    guard = BudgetGuardGateway(inner, max_calls=10, max_cost=Decimal("0.0005"))
    with pytest.raises(BudgetGuardExceeded):
        guard.chat("a")
    assert inner.calls == 0


def test_route_cases_have_unique_questions_and_known_labels() -> None:
    cases = load_route_cases()
    assert len(cases) == len({c["question"] for c in cases})
    assert {c["expected"][0] for c in cases} <= {"analyze", "needs_clarification"}


def test_routing_labels_accept_listed_alternatives_and_skip_excluded() -> None:
    from scripts.evaluation.run_planner_route_evaluation import (
        score_with_routing_labels,
    )

    results = [
        {"case_id": "a", "split": "development", "expected": "x", "actual": "alt"},
        {"case_id": "b", "split": "development", "expected": "y", "actual": "wrong"},
        {"case_id": "c", "split": "heldout", "expected": "z", "actual": "other"},
    ]
    labels = {
        "version": "v-test",
        "status": "pending_user_review",
        "cases": [
            {"case_id": "a", "included": True, "acceptable": ["x", "alt"]},
            {"case_id": "b", "included": True, "acceptable": ["y"]},
            {"case_id": "c", "included": False, "acceptable": []},
        ],
    }

    scored = score_with_routing_labels(results, labels)

    assert scored["excluded"] == 1
    assert scored["accuracy"] == 0.5
    assert scored["still_wrong"] == ["b"]


def test_routing_label_file_keeps_original_label_first_and_cites_rules() -> None:
    import json
    from pathlib import Path

    from scripts.evaluation.run_planner_route_evaluation import load_route_cases

    doc = json.loads(
        Path("tests/fixtures/evaluation_routing/planner_routes_v1.json").read_text(
            encoding="utf-8"
        )
    )
    by_id = {c["case_id"]: c for c in doc["cases"]}
    assert set(by_id) == {c["case_id"] for c in load_route_cases()}
    for case in doc["cases"]:
        assert case["rules"] and set(case["rules"]) <= set(doc["rubric"])
        if case["included"]:
            assert case["acceptable"][0] == case["original"]


def test_label_cases_take_the_first_acceptable_decision_and_skip_excluded() -> None:
    label_doc = {
        "cases": [
            {
                "case_id": "a",
                "split": "heldout",
                "question": "q",
                "acceptable": ["needs_clarification/None", "analyze/data_only"],
            },
            {"case_id": "b", "question": "r", "acceptable": [], "included": False},
        ]
    }

    assert load_label_cases(label_doc) == [
        {
            "case_id": "a",
            "split": "heldout",
            "question": "q",
            "expected": ("needs_clarification", None),
        }
    ]


def test_evaluate_keeps_the_planners_resolved_question(monkeypatch) -> None:
    # B2j: the rules read this question online, so the offline comparison must too.
    class _Planner:
        def __init__(self, **_kwargs) -> None:
            self.model_attempts = 1

        def decide(self, question):
            return SimpleNamespace(
                action="analyze", route="data_only", resolved_question=question + "!"
            )

    monkeypatch.setattr(
        "app.modules.analysis.planner.planning.PlanningService", _Planner
    )
    case = {
        "case_id": "a",
        "split": "heldout",
        "question": "q",
        "expected": ("analyze", "data_only"),
    }

    [result] = evaluate(None, [case])

    assert result["resolved_question"] == "q!"
