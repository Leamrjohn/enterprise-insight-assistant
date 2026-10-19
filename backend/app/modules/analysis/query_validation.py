"""Deterministic post-execution evidence checks for controlled SQL."""

from __future__ import annotations

from app.modules.analysis.query_contract import QueryContract, QueryResultAssessment


def assess_query_result(
    *,
    columns: list[object] | None,
    rows: list[object] | None,
    contract: QueryContract | None,
) -> QueryResultAssessment:
    """Classify evidence quality; a database success alone is not an answer."""
    normalized_columns = [str(column) for column in (columns or [])]
    normalized_rows = list(rows or [])
    if not normalized_columns:
        return QueryResultAssessment(
            status="invalid_result_shape",
            reason="查询未返回可识别的结果列。",
        )
    if not normalized_rows:
        return QueryResultAssessment(
            status="no_matching_records",
            reason="在当前筛选范围内未找到匹配记录。",
        )
    if any(
        not isinstance(row, (list, tuple)) or len(row) != len(normalized_columns)
        for row in normalized_rows
    ):
        return QueryResultAssessment(
            status="invalid_result_shape",
            reason="查询结果的列数与记录内容不一致。",
        )
    if contract is not None:
        missing_columns = [
            column
            for column in contract.expected_columns
            if column not in normalized_columns
        ]
        if missing_columns:
            return QueryResultAssessment(
                status="invalid_result_shape",
                reason="查询未返回约定的业务结果列：" + "、".join(missing_columns),
            )
        if (
            contract.result_kind == "aggregate"
            and len(normalized_rows) == 1
            and all(value is None for value in normalized_rows[0])
        ):
            return QueryResultAssessment(
                status="no_matching_records",
                reason="在当前筛选范围内未找到可聚合的匹配记录。",
            )
    return QueryResultAssessment(status="supported", reason="查询结果满足证据契约。")
