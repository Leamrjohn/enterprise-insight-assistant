from decimal import Decimal

import pytest
from app.core.gateway.base import ModelGateway
from scripts.evaluation.run_planner_route_evaluation import (
    BudgetGuardExceeded,
    BudgetGuardGateway,
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
