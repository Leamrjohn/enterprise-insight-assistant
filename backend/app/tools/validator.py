import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from app.tools.business_semantic_catalog import (
    allowed_columns as catalog_allowed_columns,
    is_allowed_join,
    is_allowed_table,
)


def validate_sql(sql: str, allowed_tables: set[str]) -> None:
    statement = _parse_single_select(sql)
    _reject_unsupported_syntax(statement)

    aliases = _validate_tables(statement, allowed_tables)
    _validate_columns(statement, aliases)
    _validate_joins(statement, aliases)


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


def _reject_unsupported_syntax(statement: exp.Select) -> None:
    if statement.args.get("with_") is not None:
        raise ValueError("暂不允许CTE查询")

    if any(statement.find_all(exp.Subquery)):
        raise ValueError("暂不允许子查询")

    if any(statement.find_all(exp.Star)):
        raise ValueError("不允许使用*，必须明确指定字段")


def _validate_tables(
    statement: exp.Select,
    allowed_tables: set[str],
) -> dict[str, str]:
    aliases: dict[str, str] = {}

    for table_node in statement.find_all(exp.Table):
        if table_node.db or table_node.catalog:
            raise ValueError("不允许指定数据库或Schema")

        table_name = table_node.name
        alias = table_node.alias_or_name

        if not is_allowed_table(table_name):
            raise ValueError(f"表 {table_name!r} 不在业务目录中")

        if table_name not in allowed_tables:
            raise ValueError(f"表 {table_name!r} 不在当前工具白名单中")

        if alias in aliases:
            raise ValueError(f"表别名 {alias!r} 重复")

        aliases[alias] = table_name

    if not aliases:
        raise ValueError("查询必须包含业务数据表")

    return aliases


def _resolve_column(
    column: exp.Column,
    aliases: dict[str, str],
) -> tuple[str, str]:
    if not column.table:
        raise ValueError(f"字段 {column.name!r} 必须使用表名或表别名前缀")

    table_name = aliases.get(column.table)
    if table_name is None:
        raise ValueError(f"未知表或别名: {column.table!r}")

    if column.name not in catalog_allowed_columns(table_name):
        raise ValueError(f"字段 {column.name!r} 不允许从表 {table_name!r} 查询")

    return table_name, column.name


def _is_select_alias_reference(
    column: exp.Column,
    select_aliases: set[str],
) -> bool:
    if column.table or column.name not in select_aliases:
        return False

    return isinstance(column.parent, exp.Group) or (
        isinstance(column.parent, exp.Ordered)
        and isinstance(column.parent.parent, exp.Order)
    )


def _validate_columns(
    statement: exp.Select,
    aliases: dict[str, str],
) -> None:
    select_aliases = {
        expression.alias
        for expression in statement.expressions
        if isinstance(expression, exp.Alias)
    }

    for column in statement.find_all(exp.Column):
        if _is_select_alias_reference(column, select_aliases):
            continue

        _resolve_column(column, aliases)


def _validate_joins(
    statement: exp.Select,
    aliases: dict[str, str],
) -> None:
    for join in statement.find_all(exp.Join):
        on_expression = join.args.get("on")

        if not isinstance(on_expression, exp.EQ):
            raise ValueError("Join 必须使用单个 表.字段 = 表.字段 的 ON 条件")

        left = on_expression.left
        right = on_expression.right

        if not isinstance(left, exp.Column) or not isinstance(right, exp.Column):
            raise ValueError("Join 条件两侧必须都是字段")

        left_table, left_column = _resolve_column(left, aliases)
        right_table, right_column = _resolve_column(right, aliases)

        if not is_allowed_join(
            left_table,
            left_column,
            right_table,
            right_column,
        ):
            raise ValueError(
                "不允许的表关联："
                f"{left_table}.{left_column} = "
                f"{right_table}.{right_column}"
            )
