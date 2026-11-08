"""Deterministically classify a bounded numeric claim against query output."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app.modules.analysis.data.query_contract import NumericAssertion


@dataclass(frozen=True)
class ClaimAssessment:
    status: str
    reason: str


def assess_numeric_assertion(
    assertion: NumericAssertion | None,
    *,
    columns: list[object],
    rows: list[object],
    metric_status: str,
) -> ClaimAssessment:
    """Return evidence status; absence or malformed output never becomes support."""
    if assertion is None:
        return ClaimAssessment("insufficient", "查询契约未声明可验证的数值断言。")
    if metric_status != "supported":
        return ClaimAssessment("insufficient", "指标口径尚未通过确定性校验。")
    column_names = [str(column) for column in columns]
    if assertion.column not in column_names:
        return ClaimAssessment("irrelevant", "断言列不在查询结果中。")
    if len(rows) != 1 or not isinstance(rows[0], (list, tuple)):
        return ClaimAssessment("insufficient", "数值断言只接受恰好一行的聚合结果。")
    row = rows[0]
    column_index = column_names.index(assertion.column)
    if column_index >= len(row):
        return ClaimAssessment("insufficient", "查询结果列数与数值断言不一致。")
    try:
        actual = Decimal(str(row[column_index]))
    except (InvalidOperation, ValueError):
        return ClaimAssessment("insufficient", "断言结果不是可比较的数值。")

    if assertion.operator == "equals":
        supported = actual == assertion.value
    elif assertion.operator == "greater_than":
        supported = actual > assertion.value
    else:
        supported = actual < assertion.value
    status = "supported" if supported else "refuted"
    return ClaimAssessment(
        status,
        "数值断言已由受控查询结果验证。"
        if supported
        else "数值断言与受控查询结果不一致。",
    )
