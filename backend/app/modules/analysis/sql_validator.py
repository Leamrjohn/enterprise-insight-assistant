"""Read-only SQL validation with a tenant snapshot table boundary."""

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from app.modules.analysis.semantic_catalog import is_allowed_table
from app.modules.analysis.snapshot_catalog import SnapshotCatalog


def validate_sql(
    sql: str,
    allowed_tables: set[str],
    *,
    catalog: SnapshotCatalog | None = None,
) -> None:
    """Accept one read-only query and keep every physical table in scope.

    CTEs, subqueries, wildcard projection and flexible joins are deliberately
    allowed.  The security invariant is instead that every physical table
    belongs to the current company's frozen schema snapshot.
    """
    statement = _parse_single_select(sql)
    _validate_tables(statement, allowed_tables, catalog)


def _parse_single_select(sql: str) -> exp.Select:
    try:
        statements = sqlglot.parse(sql, read="postgres")
    except ParseError as error:
        raise ValueError(f"SQL语法错误: {error}") from error

    if not statements:
        raise ValueError("SQL不能为空")

    if len(statements) != 1:
        raise ValueError("不允许执行多条SQL语句")

    statement = statements[0]
    if not isinstance(statement, exp.Select):
        raise ValueError("仅允许SELECT语句")

    return statement


def _validate_tables(
    statement: exp.Select,
    allowed_tables: set[str],
    catalog: SnapshotCatalog | None,
) -> None:
    """Treat CTE names as local aliases; validate every physical table."""
    cte_names = {cte.alias_or_name for cte in statement.find_all(exp.CTE)}
    physical_table_count = 0

    for table_node in statement.find_all(exp.Table):
        if table_node.db or table_node.catalog:
            raise ValueError("不允许指定数据库或Schema")

        table_name = table_node.name
        if table_name in cte_names:
            continue

        physical_table_count += 1
        if catalog is None and not is_allowed_table(table_name):
            raise ValueError(f"表 {table_name!r} 不在业务目录中")

        if catalog is not None and not catalog.has_table(table_name):
            raise ValueError(f"表 {table_name!r} 不在当前公司数据目录中")

        if table_name not in allowed_tables:
            raise ValueError(f"表 {table_name!r} 不在当前工具白名单中")

    if not physical_table_count:
        raise ValueError("查询必须包含业务数据表")
