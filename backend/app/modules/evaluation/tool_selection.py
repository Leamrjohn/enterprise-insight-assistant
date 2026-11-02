"""Score which tools a strategy would call for each question."""

from __future__ import annotations

from collections import Counter

ROUTE_TOOLS = {
    "analyze/data_only": frozenset({"sql_query"}),
    "analyze/knowledge_only": frozenset({"rag_search"}),
    "analyze/hybrid": frozenset({"sql_query", "rag_search"}),
    "needs_clarification/None": frozenset(),
    "direct_response/None": frozenset(),
    "refuse/None": frozenset(),
    "scope_exit/None": frozenset(),
}


def tools_for_decision(decision: str) -> frozenset[str] | None:
    """Tools the fixed route would call; ``None`` when the decision is unknown."""
    return ROUTE_TOOLS.get(decision)


def score_tool_case(
    *,
    called: frozenset[str] | None,
    acceptable: list[frozenset[str]],
    forbidden: frozenset[str] = frozenset(),
) -> dict:
    if called is None:
        return {"verdict": "error", "forbidden_called": []}
    forbidden_called = sorted(called & forbidden)
    if called in acceptable:
        verdict = "correct"
    elif any(called < option for option in acceptable):
        verdict = "too_few_tools"
    elif any(called > option for option in acceptable):
        verdict = "too_many_tools"
    else:
        verdict = "wrong_tools"
    return {"verdict": verdict, "forbidden_called": forbidden_called}


def summarize_tool_cases(rows: list[dict]) -> dict:
    def accuracy(subset: list[dict]) -> float | None:
        if not subset:
            return None
        return sum(r["verdict"] == "correct" for r in subset) / len(subset)

    return {
        "cases": len(rows),
        "accuracy": accuracy(rows),
        "by_split": {
            split: accuracy([r for r in rows if r["split"] == split])
            for split in sorted({r["split"] for r in rows})
        },
        "verdicts": dict(Counter(r["verdict"] for r in rows)),
        "forbidden_calls": sum(len(r["forbidden_called"]) for r in rows),
        "not_correct": [r["case_id"] for r in rows if r["verdict"] != "correct"],
    }
