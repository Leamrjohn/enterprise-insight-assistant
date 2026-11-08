"""Score generated-SQL results against a hand-written reference result.

Column names and aliases vary between correct queries, so rows are compared by
value: every reference value must appear in the matching actual row.  SQL text
is never compared; only the business result counts.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

PASSING_VERDICTS = frozenset({"correct", "correct_extra_columns", "correct_no_data"})
_AMOUNT = Decimal("0.01")


def _number(value: object) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal, str)):
        return None
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        return None
    if not number.is_finite():
        return None
    return format(number.quantize(_AMOUNT) + 0, "f")


def _row_values(row: Sequence[object], *, compare_text: bool) -> Counter:
    values: Counter = Counter()
    for value in row:
        if value is None or isinstance(value, (date, datetime)):
            continue
        number = _number(value)
        if number is not None:
            values[number] += 1
        elif compare_text:
            values[str(value).strip()] += 1
    return values


def _is_no_data(rows: Sequence[Sequence[object]]) -> bool:
    return not rows or (len(rows) == 1 and all(value is None for value in rows[0]))


def _matches(
    reference: Sequence[Counter], actual: Sequence[Counter], *, ordered: bool
) -> bool:
    if ordered:
        return all(not (r - a) for r, a in zip(reference, actual, strict=True))
    unused = list(actual)
    for row in reference:
        match = next((a for a in unused if not (row - a)), None)
        if match is None:
            return False
        unused.remove(match)
    return True


def score_result(
    *,
    expect: str,
    agent_success: bool,
    actual_rows: Sequence[Sequence[object]] | None,
    reference_rows: Sequence[Sequence[object]] | None = None,
    ordered: bool = False,
    compare_text: bool = False,
    error_code: str | None = None,
) -> str:
    """Return one verdict for a case; ``PASSING_VERDICTS`` lists those that pass."""
    if expect == "rejected":
        return "correct" if actual_rows is None else "answered_should_reject"
    if expect == "no_data":
        if error_code == "no_matching_records":
            return "correct_no_data"
        if actual_rows is None:
            return "failed_" + (error_code or "unknown")
        return "correct_no_data" if _is_no_data(actual_rows) else "value_for_no_data"
    if actual_rows is None or not agent_success:
        return "failed_" + (error_code or "unknown")
    if _is_no_data(actual_rows):
        return "false_empty"

    references = list(reference_rows or [])
    reference = [_row_values(r, compare_text=compare_text) for r in references]
    actual = [_row_values(r, compare_text=compare_text) for r in actual_rows]
    if len(actual) != len(reference):
        wanted = sum(reference, Counter())
        found = sum(actual, Counter())
        return "same_values_other_shape" if not wanted - found else "wrong_row_count"
    if not _matches(reference, actual, ordered=ordered):
        return "wrong_values"
    extra = any(len(a) > len(r) for a, r in zip(actual_rows, references, strict=True))
    return "correct_extra_columns" if extra else "correct"


def summarize(results: Iterable[dict]) -> dict:
    rows = list(results)

    def accuracy(subset: list[dict]) -> float | None:
        if not subset:
            return None
        return sum(r["verdict"] in PASSING_VERDICTS for r in subset) / len(subset)

    return {
        "cases": len(rows),
        "accuracy": accuracy(rows),
        "by_split": {
            split: accuracy([r for r in rows if r["split"] == split])
            for split in sorted({r["split"] for r in rows})
        },
        "verdicts": dict(Counter(r["verdict"] for r in rows)),
        "not_passed": [
            r["case_id"] for r in rows if r["verdict"] not in PASSING_VERDICTS
        ],
    }
