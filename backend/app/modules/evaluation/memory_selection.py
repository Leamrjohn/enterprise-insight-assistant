"""Score which memories a selector hands to the model for each question."""

from __future__ import annotations

from collections.abc import Iterable


def score_memory_case(
    *, selected: set[str], must_select: Iterable[str], must_not_select: Iterable[str]
) -> dict:
    required = set(must_select)
    forbidden = set(must_not_select)
    return {
        "missed": sorted(required - selected),
        "violations": sorted(forbidden & selected),
        "selected_count": len(selected),
        "passed": required <= selected and not forbidden & selected,
    }


def summarize_memory_cases(rows: list[dict]) -> dict:
    required = sum(len(r["missed"]) + len(r["found"]) for r in rows)
    found = sum(len(r["found"]) for r in rows)
    return {
        "cases": len(rows),
        "passed": sum(r["passed"] for r in rows),
        "required_recall": found / required if required else None,
        "violations": sum(len(r["violations"]) for r in rows),
        "isolation_violations": sum(len(r["isolation_violations"]) for r in rows),
        "average_selected": (
            sum(r["selected_count"] for r in rows) / len(rows) if rows else None
        ),
        "failed": [r["case_id"] for r in rows if not r["passed"]],
    }
