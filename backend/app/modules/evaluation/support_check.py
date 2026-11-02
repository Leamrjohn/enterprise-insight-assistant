"""Score the sentence support check against hand-labelled sentences."""

from __future__ import annotations

# Fixed before the first recording.
CITATION_SUPPORT_TARGET = 0.95
WRONGLY_REMOVED_LIMIT = 0.15


def summarize_support_cases(rows: list[dict]) -> dict:
    """citation_support_rate: of the sentences kept, how many deserved it."""
    if not rows:
        raise ValueError("support evaluation has no cases")
    should_keep = [r for r in rows if r["expected"] == "keep"]
    should_remove = [r for r in rows if r["expected"] == "remove"]
    kept = [r for r in rows if r["kept"]]
    wrongly_kept = [r for r in should_remove if r["kept"]]
    wrongly_removed = [r for r in should_keep if not r["kept"]]
    support_rate = (len(kept) - len(wrongly_kept)) / len(kept) if kept else None
    removed_rate = len(wrongly_removed) / len(should_keep) if should_keep else 0.0
    return {
        "cases": len(rows),
        "citation_support_rate": support_rate,
        "wrongly_removed_rate": removed_rate,
        "wrongly_kept": [r["case_id"] for r in wrongly_kept],
        "wrongly_removed": [r["case_id"] for r in wrongly_removed],
        "meets_target": support_rate is not None
        and support_rate >= CITATION_SUPPORT_TARGET
        and removed_rate <= WRONGLY_REMOVED_LIMIT,
    }


def summarize_end_to_end(rows: list[dict]) -> dict:
    """Effect on real answers: right answers must survive, stale ones must not."""
    answered = [r for r in rows if r["answer_before_check"]]
    return {
        "cases": len(rows),
        "answer_before_check": len(answered),
        "answer_after_check": sum(r["answer_after_check"] for r in rows),
        "answer_lost_by_check": [
            r["case_id"] for r in answered if not r["answer_after_check"]
        ],
        "answer_in_cited_chunk": sum(r["answer_in_cited_chunk"] for r in rows),
        "stale_citations": sum(r["stale_cited"] for r in rows),
        "sentences": sum(r["sentences"] for r in rows),
        "sentences_removed": sum(r["sentences_removed"] for r in rows),
        "no_supported_claim": [r["case_id"] for r in rows if not r["cited"]],
    }
