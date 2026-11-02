"""Scoring rules for the support check evaluation and its fixture integrity."""

import json
from pathlib import Path

from app.modules.evaluation.support_check import (
    summarize_end_to_end,
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


def test_fixture_has_both_labels_in_both_splits():
    cases = json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]
    ids = [case["case_id"] for case in cases]
    assert len(ids) == len(set(ids))
    for split in ("development", "heldout"):
        labels = {case["expected"] for case in cases if case["split"] == split}
        assert labels == {"keep", "remove"}
