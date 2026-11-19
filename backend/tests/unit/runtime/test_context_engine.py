"""C4: build_context runs every step in order and never lets an oversized call through."""

import pytest
from app.modules.runtime.context.engine import (
    ContextBudgetExceeded,
    ContextPolicy,
    SectionRule,
    build_context,
    count_tokens,
    require_fit,
)

QUESTION = "华东区2025年8月已交付订单销售额是多少？"


def _quarter(text: str) -> str:
    return text[: len(text) // 4]


def _policy(budget: int, **kwargs) -> ContextPolicy:
    sections = kwargs.pop("sections")
    return ContextPolicy(
        node="t", version="t/1", budget_tokens=budget, sections=sections, **kwargs
    )


def _actions(build) -> dict:
    return {
        entry.name: (entry.action, entry.reason) for entry in build.manifest.sections
    }


def test_what_fits_is_sent_untouched():
    sections = {"question": QUESTION, "memory": "上次问的是华北"}
    policy = _policy(
        4000,
        sections={"memory": SectionRule(droppable=True), "question": SectionRule()},
    )
    build = build_context(policy, sections)
    assert build.verdict == "fits"
    assert build.payload == sections
    assert _actions(build) == {"question": ("kept", None), "memory": ("kept", None)}


def test_a_section_over_its_own_cap_is_shrunk_even_far_below_budget():
    docs = "片段内容" * 200
    policy = _policy(
        100_000,
        sections={
            "docs": SectionRule(compress=_quarter, max_tokens=50),
            "question": SectionRule(),
        },
    )
    build = build_context(policy, {"docs": docs, "question": QUESTION})
    assert build.payload["docs"] == _quarter(docs)
    assert _actions(build)["docs"] == ("compressed", "section_cap")
    assert build.verdict == "fits"


def test_near_the_budget_only_as_many_sections_shrink_as_needed():
    rows, docs = "行" * 3000, "文" * 300
    shrunk = {"rows": _quarter(rows), "docs": docs, "question": QUESTION}
    policy = _policy(
        int(count_tokens(shrunk) / 0.8) + 20,
        sections={
            "rows": SectionRule(compress=_quarter),
            "docs": SectionRule(compress=_quarter),
            "question": SectionRule(),
        },
    )
    build = build_context(policy, {"rows": rows, "docs": docs, "question": QUESTION})
    assert _actions(build)["rows"] == ("compressed", "near_budget")
    assert _actions(build)["docs"] == ("kept", None)
    assert build.verdict == "fits"


def test_a_droppable_section_goes_when_nothing_else_makes_it_fit():
    memory = "记忆" * 2000
    policy = _policy(
        count_tokens({"question": QUESTION}) + 5,
        sections={"memory": SectionRule(droppable=True), "question": SectionRule()},
    )
    build = build_context(policy, {"memory": memory, "question": QUESTION})
    assert build.verdict == "fits"
    assert "memory" not in build.payload
    assert _actions(build)["memory"] == ("dropped", "over_budget")
    entry = next(e for e in build.manifest.sections if e.name == "memory")
    assert entry.final_tokens == 0 and entry.content_hash is None
    assert build.manifest.over_budget is False


def test_only_as_many_sections_are_dropped_as_needed():
    memory, history = "记忆" * 2000, "上一轮问的是华北"
    policy = _policy(
        count_tokens({"history": history, "question": QUESTION}) + 2,
        sections={
            "memory": SectionRule(droppable=True),
            "history": SectionRule(droppable=True),
            "question": SectionRule(),
        },
    )
    build = build_context(
        policy, {"memory": memory, "history": history, "question": QUESTION}
    )
    assert build.verdict == "fits"
    assert _actions(build)["memory"] == ("dropped", "over_budget")
    assert _actions(build)["history"] == ("kept", None)


def test_what_cannot_be_dropped_is_rejected_not_sent():
    policy = _policy(50, sections={"question": SectionRule()})
    build = build_context(policy, {"question": "问" * 2000})
    assert build.verdict == "reject"
    assert build.manifest.over_budget is True
    with pytest.raises(ContextBudgetExceeded) as raised:
        require_fit(build)
    assert raised.value.action == "reject"
    assert raised.value.build is build


def test_a_planner_style_policy_asks_instead_of_failing():
    policy = _policy(50, sections={"question": SectionRule()}, on_over_budget="clarify")
    build = build_context(policy, {"question": "问" * 2000})
    assert build.verdict == "clarify"
    with pytest.raises(ContextBudgetExceeded) as raised:
        require_fit(build)
    assert raised.value.action == "clarify"


def test_the_answer_reserve_comes_out_of_the_budget():
    budget = count_tokens({"question": QUESTION}) + 10
    sections = {"question": SectionRule()}
    assert build_context(
        _policy(budget, sections=sections), {"question": QUESTION}
    ).fits
    reserved = _policy(budget, sections=sections, output_reserve_tokens=20)
    assert build_context(reserved, {"question": QUESTION}).verdict == "reject"


def test_a_missing_required_section_is_a_caller_bug():
    policy = _policy(4000, sections={"question": SectionRule(required=True)})
    with pytest.raises(ValueError, match="question"):
        build_context(policy, {})


def test_an_undeclared_section_is_left_out_not_dropped():
    policy = _policy(4000, sections={"question": SectionRule()})
    build = build_context(policy, {"question": QUESTION, "secret": "内部口径"})
    assert _actions(build)["secret"] == ("left_out", "not_in_policy")
    assert "secret" not in build.payload


def test_the_same_input_gives_the_same_result():
    memory = "记忆" * 2000
    policy = _policy(
        count_tokens({"question": QUESTION}) + 5,
        sections={"memory": SectionRule(droppable=True), "question": SectionRule()},
    )
    sections = {"memory": memory, "question": QUESTION}
    first, second = build_context(policy, sections), build_context(policy, sections)
    assert first.payload == second.payload
    assert first.manifest.to_record() == second.manifest.to_record()
