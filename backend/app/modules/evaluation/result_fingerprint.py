"""Build a stable fingerprint from validated SQL result evidence."""

import hashlib
import json
import re
from decimal import Decimal, InvalidOperation

_COMPARISON_PERIOD = re.compile(
    r"^(?P<current>\d{4}-\d{2}) compared_to (?P<comparison>\d{4}-\d{2})$"
)
_MONTH_VALUE = re.compile(r"^(?P<month>\d{4}-(?:0[1-9]|1[0-2]))(?:-01)?$")
_MONTH_COLUMNS = frozenset({"month", "月份"})
_REVENUE_COLUMNS = frozenset({"revenue", "sales_amount", "销售额"})


def _canonical_columns(item: dict[str, object], columns: list[str]) -> list[str]:
    """Keep a validated one-metric result stable when its SQL alias varies."""
    contract = item.get("query_contract")
    concepts = contract.get("required_concepts") if isinstance(contract, dict) else None
    if (
        len(columns) == 1
        and isinstance(concepts, list)
        and len(concepts) == 1
        and isinstance(concepts[0], str)
        and concepts[0].strip()
    ):
        return [concepts[0]]
    return columns


def result_fingerprint_from_data_result(
    data_result: object,
) -> dict[str, str] | None:
    """Return a SHA-256 fingerprint, or ``None`` when no result is provable.

    SQL text and agent rationale are intentionally excluded: they describe an
    execution path, not the returned business result. A validated empty SQL
    result is also a business result, so retain its explicit no-match status.
    """
    if not isinstance(data_result, dict):
        return None
    if data_result.get("status") == "insufficient_evidence":
        if data_result.get("error_code") != "no_matching_records":
            return None
        canonical_evidence: list[dict[str, object]] = [
            {"error_code": "no_matching_records", "status": "insufficient_evidence"}
        ]
    else:
        if data_result.get("status") != "ready":
            return None
        evidence = data_result.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            return None
        canonical_evidence = []
        for item in evidence:
            if not isinstance(item, dict):
                return None
            columns = item.get("columns")
            rows = item.get("rows")
            if (
                not isinstance(columns, list)
                or not all(isinstance(column, str) for column in columns)
                or not isinstance(rows, list)
                or any(
                    not isinstance(row, list) or len(row) != len(columns)
                    for row in rows
                )
            ):
                return None
            canonical_evidence.append(
                {"columns": _canonical_columns(item, columns), "rows": rows}
            )

    try:
        canonical_json = json.dumps(
            canonical_evidence,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError):
        return None

    return {
        "algorithm": "sha256",
        "value": hashlib.sha256(canonical_json.encode("utf-8")).hexdigest(),
    }


def revenue_month_comparison_fingerprint_from_data_result(
    data_result: object, *, period: object
) -> dict[str, str] | None:
    """Hash one validated two-month ``revenue/v1`` result, or fail closed."""
    months = _comparison_months(period)
    if (
        months is None
        or not isinstance(data_result, dict)
        or data_result.get("status") != "ready"
    ):
        return None
    evidence = data_result.get("evidence")
    if not isinstance(evidence, list) or len(evidence) != 1:
        return None
    item = evidence[0]
    if not isinstance(item, dict) or not _is_supported_revenue_evidence(item):
        return None
    columns = item.get("columns")
    rows = item.get("rows")
    if (
        not isinstance(columns, list)
        or len(columns) != 2
        or not all(isinstance(column, str) for column in columns)
        or not isinstance(rows, list)
        or len(rows) != 2
    ):
        return None
    normalized_columns = [column.strip().casefold() for column in columns]
    if (
        len(set(normalized_columns)) != 2
        or sum(column in _MONTH_COLUMNS for column in normalized_columns) != 1
        or sum(column in _REVENUE_COLUMNS for column in normalized_columns) != 1
    ):
        return None
    month_index = next(
        index
        for index, column in enumerate(normalized_columns)
        if column in _MONTH_COLUMNS
    )
    revenue_index = 1 - month_index
    month_revenue: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, list) or len(row) != 2:
            return None
        month = _canonical_month(row[month_index])
        revenue = _canonical_revenue(row[revenue_index])
        if month is None or revenue is None or month in month_revenue:
            return None
        month_revenue[month] = revenue
    if set(month_revenue) != set(months):
        return None
    canonical_json = json.dumps(
        {
            "metric_definition_ref": "revenue/v1",
            "month_revenue": [
                [month, month_revenue[month]] for month in sorted(months)
            ],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return {
        "algorithm": "sha256",
        "value": hashlib.sha256(canonical_json.encode("utf-8")).hexdigest(),
    }


def _comparison_months(period: object) -> tuple[str, str] | None:
    if not isinstance(period, str):
        return None
    match = _COMPARISON_PERIOD.fullmatch(period)
    if match is None:
        return None
    months = (match["current"], match["comparison"])
    return months if months[0] != months[1] else None


def _is_supported_revenue_evidence(item: dict[str, object]) -> bool:
    assessment = item.get("metric_assessment")
    return (
        isinstance(assessment, dict)
        and assessment.get("status") == "supported"
        and assessment.get("metric_definition_ref") == "revenue/v1"
    )


def _canonical_month(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    match = _MONTH_VALUE.fullmatch(value)
    return match["month"] if match is not None else None


def _canonical_revenue(value: object) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        return None
    try:
        decimal_value = Decimal(str(value))
    except InvalidOperation:
        return None
    if not decimal_value.is_finite():
        return None
    normalized = decimal_value.quantize(Decimal("0.01"))
    if decimal_value != normalized:
        return None
    return format(Decimal(0) if normalized == 0 else normalized, "f")
