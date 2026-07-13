"""SQL 数据查询工具"""

from app.tools.protocol import Tool, ToolInput, ToolOutput
from app.tools.executor import execute_readonly_sql


ALLOWED_TABLES = {"customers", "products", "orders", "order_items", "complaints"}


class SQLTool(Tool):
    """基于只读SQL查询经营数据的工具"""

    @property
    def name(self) -> str:
        return "sql_query"

    @property
    def description(self) -> str:
        return "使用SQL查询经营数据库。允许的表：customers, products, orders, order_items, complaints"

    def execute(self, input: ToolInput) -> ToolOutput:
        sql = input.parameters.get("sql")
        if not sql:
            return ToolOutput(success=False, error="缺少 sql 参数")

        try:
            columns, rows = execute_readonly_sql(sql, allowed_tables=ALLOWED_TABLES)
            return ToolOutput(success=True, data={"columns": columns, "rows": rows})
        except ValueError as e:
            return ToolOutput(success=False, error=str(e))
