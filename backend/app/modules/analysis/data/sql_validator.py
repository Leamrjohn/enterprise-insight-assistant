"""Read-only SQL validation with a tenant snapshot table boundary."""

import sqlglot
from app.modules.analysis.catalog.semantic_catalog import is_allowed_table
from app.modules.analysis.catalog.snapshot_catalog import SnapshotCatalog
from sqlglot import exp
from sqlglot.errors import ParseError


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
    _validate_no_side_effects(statement)
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
        # The caller supplied SQL text; its statement kind violates the value contract.
        raise ValueError("仅允许SELECT语句")  # noqa: TRY004

    return statement


# A top-level SELECT can still carry writes (data-modifying CTEs, SELECT INTO),
# row locks, or server-side functions with side effects.  The read-only role
# and transaction would stop most of them; this layer must not rely on that.
_WRITE_NODE_NAMES = (
    "Insert",
    "Update",
    "Delete",
    "Merge",
    "Create",
    "Drop",
    "Alter",
    "AlterTable",
    "Command",
    "Into",
)
_WRITE_NODES = tuple(
    getattr(exp, name) for name in _WRITE_NODE_NAMES if hasattr(exp, name)
)
_DENIED_FUNCTION_PREFIXES = ("pg_", "lo_", "dblink", "txid_")
_DENIED_FUNCTIONS = frozenset(
    {
        "set_config",
        "current_setting",
        "query_to_xml",
        "query_to_xml_and_xmlschema",
        "table_to_xml",
        "cursor_to_xml",
    }
)


def _function_names(node: exp.Func) -> set[str]:
    names = {node.sql_name().lower()}
    if isinstance(node, exp.Anonymous):
        names.add(str(node.name).lower())
    return names


def _validate_no_side_effects(statement: exp.Select) -> None:
    # ValueError is this module's rejection contract for unsafe SQL text.
    for node in statement.walk():
        if isinstance(node, _WRITE_NODES):
            raise ValueError("查询中不允许包含写入或结构修改语句")  # noqa: TRY004
        if isinstance(node, exp.Lock):
            raise ValueError("查询中不允许加锁（FOR UPDATE / FOR SHARE）")  # noqa: TRY004
        if isinstance(node, exp.Func):
            for name in _function_names(node):
                if name in _DENIED_FUNCTIONS or name.startswith(
                    _DENIED_FUNCTION_PREFIXES
                ):
                    raise ValueError(f"函数 {name} 不允许在业务查询中使用")


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
