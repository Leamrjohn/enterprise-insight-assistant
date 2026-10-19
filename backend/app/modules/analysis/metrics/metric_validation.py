"""Deterministic metric, time, unit, and SQL-lineage validation."""

import re
from dataclasses import dataclass
from datetime import date

import sqlglot
from app.modules.analysis.metrics.metric_catalog import MetricDefinition, get_metric_definition
from app.modules.analysis.data.query_contract import QueryContract
from sqlglot import exp
from sqlglot.errors import ParseError


@dataclass(frozen=True)
class MetricQueryAssessment:
    status: str
    reason: str
    definition: MetricDefinition | None
    lineage_columns: tuple[str, ...]


def assess_metric_query(
    sql: str,
    contract: QueryContract | None,
    *,
    evaluation_scope: dict[str, object] | None = None,
) -> MetricQueryAssessment:
    """Accept only a declared metric whose technical lineage is visible in SQL."""
    if contract is None or contract.metric_definition_ref is None:
        return MetricQueryAssessment(
            status="insufficient",
            reason="查询契约未声明指标定义引用。",
            definition=None,
            lineage_columns=(),
        )
    definition = get_metric_definition(contract.metric_definition_ref)
    if definition is None:
        return MetricQueryAssessment(
            status="irrelevant",
            reason="查询引用了未注册的指标定义。",
            definition=None,
            lineage_columns=(),
        )
    if contract.time_scope_column != definition.time_column:
        return MetricQueryAssessment(
            status="insufficient",
            reason="查询契约的时间列与指标定义不一致。",
            definition=definition,
            lineage_columns=(),
        )
    try:
        statements = sqlglot.parse(sql, read="postgres")
    except ParseError:
        return MetricQueryAssessment(
            status="irrelevant",
            reason="无法从候选 SQL 提取指标血缘。",
            definition=definition,
            lineage_columns=(),
        )
    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        return MetricQueryAssessment(
            status="irrelevant",
            reason="指标血缘只接受单条 SELECT。",
            definition=definition,
            lineage_columns=(),
        )
    statement = statements[0]
    aliases = {
        table.alias_or_name: table.name for table in statement.find_all(exp.Table)
    }
    lineage_columns = tuple(
        sorted(
            {
                _canonical_column(column, aliases)
                for column in statement.find_all(exp.Column)
                if column.table
            }
        )
    )
    if not _has_required_aggregate(statement, aliases, definition):
        return MetricQueryAssessment(
            status="insufficient",
            reason=(
                "候选 SQL 未按指标定义聚合："
                f"{definition.aggregate_function}({definition.aggregate_source_column})"
            ),
            definition=definition,
            lineage_columns=lineage_columns,
        )
    for column, expected_value in definition.mandatory_equals:
        if not _has_required_equality(statement, aliases, column, expected_value):
            return MetricQueryAssessment(
                status="insufficient",
                reason=f"候选 SQL 缺少指标定义要求的筛选：{column} = {expected_value}",
                definition=definition,
                lineage_columns=lineage_columns,
            )
    missing_columns = sorted(definition.source_columns - set(lineage_columns))
    if missing_columns:
        return MetricQueryAssessment(
            status="insufficient",
            reason="候选 SQL 缺少指标定义要求的血缘列：" + "、".join(missing_columns),
            definition=definition,
            lineage_columns=lineage_columns,
        )
    scope_reason = _comparison_scope_reason(
        statement,
        aliases=aliases,
        contract=contract,
        evaluation_scope=evaluation_scope,
    )
    if scope_reason is not None:
        return MetricQueryAssessment(
            status="incomplete",
            reason=scope_reason,
            definition=definition,
            lineage_columns=lineage_columns,
        )
    return MetricQueryAssessment(
        status="supported",
        reason="指标定义、业务时间列和 SQL 技术血缘一致。",
        definition=definition,
        lineage_columns=lineage_columns,
    )


def _comparison_scope_reason(
    statement: exp.Select,
    *,
    aliases: dict[str, str],
    contract: QueryContract,
    evaluation_scope: dict[str, object] | None,
) -> str | None:
    """Require a frozen two-month scope to appear in the SQL time predicate."""
    if not isinstance(evaluation_scope, dict):
        return None
    period = evaluation_scope.get("period")
    if not isinstance(period, str):
        return None
    match = re.fullmatch(
        r"(20\d{2})-(0[1-9]|1[0-2])\s+compared_to\s+"
        r"(20\d{2})-(0[1-9]|1[0-2])",
        period,
    )
    if match is None:
        return None
    current = f"{match.group(1)}-{match.group(2)}"
    comparison = f"{match.group(3)}-{match.group(4)}"
    where = statement.args.get("where")
    if where is None or not any(
        _canonical_column(column, aliases) == contract.time_scope_column
        for column in where.find_all(exp.Column)
    ):
        return "候选 SQL 未在 WHERE 条件中使用冻结的业务时间列。"
    literal_months = {
        item.this[:7]
        for item in where.find_all(exp.Literal)
        if item.is_string
        and re.fullmatch(r"20\d{2}-(?:0[1-9]|1[0-2])(?:-\d{2})?", item.this)
    }
    expected_months = {current, comparison}
    if expected_months.issubset(literal_months):
        return None
    lower_month, upper_month = min(expected_months), max(expected_months)
    if {lower_month, _next_month(upper_month)}.issubset(literal_months):
        return None
    return (
        "候选 SQL 的时间谓词未覆盖冻结的比较月份："
        f"{comparison} 与 {current}。"
    )


def _next_month(month: str) -> str:
    value = date.fromisoformat(f"{month}-01")
    return (
        f"{value.year + 1}-01"
        if value.month == 12
        else f"{value.year}-{value.month + 1:02d}"
    )


def _canonical_column(column: exp.Column, aliases: dict[str, str]) -> str:
    return f"{aliases.get(column.table, column.table)}.{column.name}"


def _has_required_equality(
    statement: exp.Select,
    aliases: dict[str, str],
    expected_column: str,
    expected_value: str,
) -> bool:
    for equality in statement.find_all(exp.EQ):
        left, right = equality.left, equality.right
        for column, value in ((left, right), (right, left)):
            if not isinstance(column, exp.Column) or not isinstance(value, exp.Literal):
                continue
            if (
                _canonical_column(column, aliases) == expected_column
                and value.this == expected_value
            ):
                return True
    return False


def _has_required_aggregate(
    statement: exp.Select,
    aliases: dict[str, str],
    definition: MetricDefinition,
) -> bool:
    aggregate_type = exp.Sum if definition.aggregate_function == "SUM" else exp.Count
    for aggregate in statement.find_all(aggregate_type):
        argument = aggregate.this
        if isinstance(argument, exp.Column) and (
            _canonical_column(argument, aliases) == definition.aggregate_source_column
        ):
            return True
    return False
