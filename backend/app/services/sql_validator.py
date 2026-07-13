import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError


def validate_sql(sql: str, allowed_tables: set[str], allowed_columns: set[str]):
    """验证SQL是否安全，不安全则抛出异常"""
    # 1. 解析SQL —— 如果语法错误会抛 ParseError
    # 2. 检查是不是单条语句
    # 3. 检查是不是 SELECT（不是就拒绝）
    # 4. 检查表名在白名单中
    # 5. 检查列名在白名单中（可选，初版可跳过）
    try:
        parsed = sqlglot.parse(sql)
    except ParseError as e:
        raise ValueError(f"SQL语法错误: {e}")
    if len(parsed) == 0:
        raise ValueError("SQL为空")
    if len(parsed) > 1:
        raise ValueError("不允许执行多条SQL语句")
    statement = parsed[0]
    if not isinstance(statement, exp.Select):
        raise ValueError(f"仅允许SELECT语句，实际类型: {type(statement).__name__}")

    # 4. 检查表名在白名单中
    table_nodes = statement.find_all(exp.Table)
    tables = [t.name for t in table_nodes]
    for t in tables:
        if t not in allowed_tables:
            raise ValueError(f"表 '{t}' 不在白名单中。允许的表: {allowed_tables}")
