"""Scoring rules for the support check evaluation and its fixture integrity."""

import json
from pathlib import Path

import pytest
from app.modules.evaluation.support_check import (
    answer_matches_loosely,
    summarize_end_to_end,
    summarize_loose_answers,
    summarize_support_cases,
)

FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "evaluation_support"
    / "support_cases_v1.json"
)


def _row(case_id, expected, kept):
    return {"case_id": case_id, "expected": expected, "kept": kept}


def test_support_rate_counts_only_kept_sentences():
    summary = summarize_support_cases(
        [
            _row("a", "keep", True),
            _row("b", "keep", False),
            _row("c", "remove", True),
            _row("d", "remove", False),
        ]
    )
    assert summary["citation_support_rate"] == 0.5
    assert summary["wrongly_removed_rate"] == 0.5
    assert summary["wrongly_kept"] == ["c"]
    assert summary["wrongly_removed"] == ["b"]
    assert not summary["meets_target"]


def test_removing_everything_does_not_meet_the_target():
    summary = summarize_support_cases(
        [_row("a", "keep", False), _row("b", "remove", False)]
    )
    assert summary["citation_support_rate"] is None
    assert not summary["meets_target"]


def test_meets_target_when_both_lines_hold():
    summary = summarize_support_cases(
        [_row("a", "keep", True), _row("b", "remove", False)]
    )
    assert summary["meets_target"]


def test_end_to_end_reports_answers_lost_and_stale_citations():
    base = {
        "answer_in_cited_chunk": True,
        "stale_cited": 0,
        "cited": True,
        "sentences": 2,
        "sentences_removed": 1,
    }
    summary = summarize_end_to_end(
        [
            {
                **base,
                "case_id": "a",
                "answer_before_check": True,
                "answer_after_check": False,
            },
            {
                **base,
                "case_id": "b",
                "answer_before_check": True,
                "answer_after_check": True,
                "stale_cited": 1,
                "cited": False,
            },
        ]
    )
    assert summary["answer_lost_by_check"] == ["a"]
    assert summary["stale_citations"] == 1
    assert summary["no_supported_claim"] == ["b"]


@pytest.mark.parametrize(
    ("expected", "answer"),
    [
        ("147 笔", "2025年7月已交付订单为147笔。"),
        ("约 12%", "约12%"),
        ("约 12%", "约１２％"),
        ("供应商：24 家；成本中心：5 个", "供应商 24 家，成本中心 5 个。"),
        ("1,286 单", "共 1286 单"),
    ],
)
def test_loose_match_ignores_spaces_and_punctuation(expected, answer):
    assert answer_matches_loosely(expected, answer)


@pytest.mark.parametrize(
    ("expected", "answer"),
    [
        ("147 笔", "共 1147 笔"),
        ("147 笔", "共 1,147 笔"),
        ("36 件", "共 136 件"),
        ("5 个", "约 0.5 个"),
        ("4.20", "评分 420"),
        ("12", "上调 12.5%"),
        ("12%", "上调 12.5%"),
        ("147 笔", "资料里没有"),
        # Other words between the facts still count as a different wording.
        ("高优先级工单5件", "高优先级工单有5件"),
        ("", "任何回答"),
    ],
)
def test_loose_match_does_not_accept_a_different_number_or_wording(expected, answer):
    assert not answer_matches_loosely(expected, answer)


def test_loose_summary_lists_answers_only_the_loose_score_accepts():
    summary = summarize_loose_answers(
        [
            {"case_id": "a", "answer_after_check": True, "answer_loose": True},
            {"case_id": "b", "answer_after_check": False, "answer_loose": True},
            {"case_id": "c", "answer_after_check": False, "answer_loose": False},
        ]
    )
    assert summary == {"answer_after_check_loose": 2, "accepted_only_by_loose": ["b"]}


def test_case_row_scores_the_final_answer_both_ways():
    from types import SimpleNamespace

    from scripts.evaluation.run_support_evaluation import _case_row

    output = SimpleNamespace(answer="已交付147笔。", evidence=[], error_code=None)

    row = _case_row("a", "147 笔", output, [])

    assert row["answer_after_check"] is False
    assert row["answer_loose"] is True


def test_fixture_has_both_labels_in_both_splits():
    cases = json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]
    ids = [case["case_id"] for case in cases]
    assert len(ids) == len(set(ids))
    for split in ("development", "heldout"):
        labels = {case["expected"] for case in cases if case["split"] == split}
        assert labels == {"keep", "remove"}
