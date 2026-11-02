"""The retrieval labels must be checkable, and the trap scorer must count correctly."""

import json
from pathlib import Path

from app.modules.evaluation.retrieval import answer_hit_rates, score_version_traps

BACKEND = Path(__file__).resolve().parents[3]
CORPUS = BACKEND.parent / "data" / "business_knowledge_base"
FIXTURES = BACKEND / "tests" / "fixtures" / "evaluation_retrieval"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_every_gold_answer_appears_in_a_relevant_document():
    for case in _load("retrieval_gold_v2.json")["cases"]:
        texts = [
            (CORPUS / path).read_text(encoding="utf-8") for path in case["relevant"]
        ]
        assert any(case["answer"] in text for text in texts), case["case_id"]


def test_gold_case_ids_are_unique_and_keep_a_heldout_split():
    cases = _load("retrieval_gold_v2.json")["cases"]
    assert len({case["case_id"] for case in cases}) == len(cases)
    assert sum(case["split"] == "heldout" for case in cases) >= 10


def test_each_trap_answer_is_only_in_the_applicable_version():
    fixture = _load("version_traps_v1.json")
    documents = {doc["key"]: doc for doc in fixture["documents"]}
    for case in fixture["cases"]:
        assert case["answer"] in documents[case["fresh"]]["content"], case["case_id"]
        assert case["answer"] not in documents[case["stale"]]["content"], case[
            "case_id"
        ]


def test_historical_traps_fall_inside_the_applicable_version():
    fixture = _load("version_traps_v1.json")
    documents = {doc["key"]: doc for doc in fixture["documents"]}
    for case in fixture["cases"]:
        if case["kind"] != "as_of":
            continue
        right = documents[case["fresh"]]
        wrong = documents[case["stale"]]
        assert right["effective_from"] <= case["as_of"] <= right["effective_to"]
        assert case["as_of"] < wrong["effective_from"]


def test_answer_hit_rates_report_misses_by_split():
    result = answer_hit_rates(
        [
            {"case_id": "a", "split": "development", "found": True},
            {"case_id": "b", "split": "heldout", "found": False},
        ]
    )
    assert result["rate"] == 0.5
    assert result["by_split"] == {"development": 1.0, "heldout": 0.0}
    assert result["misses"] == ["b"]


def test_trap_score_counts_wrong_version_positions():
    def row(kind, ranked, found=True):
        return {
            "kind": kind,
            "ranked": ranked,
            "fresh": 1,
            "stale": 2,
            "answer_found": found,
        }

    overall = score_version_traps(
        [
            row("current", [1, 2]),
            row("current", [2, 1]),
            row("as_of", [2], found=False),
            row("as_of", [1]),
        ]
    )["overall"]

    assert overall == {
        "cases": 4,
        "right_version_first": 2,
        "wrong_version_retrieved": 3,
        "wrong_version_above_right": 2,
        "answer_found": 3,
    }
