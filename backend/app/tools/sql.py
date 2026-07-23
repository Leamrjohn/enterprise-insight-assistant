"""SQL 数据查询工具"""

from app.tools.protocol import Tool, ToolInput, ToolOutput
from app.tools.executor import execute_readonly_sql
from app.tools.business_semantic_catalog import BUSINESS_TABLES
from psycopg.errors import GroupingError

ALLOWED_TABLES = set(BUSINESS_TABLES)


class SQLTool(Tool):
    """基于只读SQL查询经营数据的工具"""

    @property
    def name(self) -> str:
        return "sql_query"

    @property
    def description(self) -> str:
        return "使用 SQL 查询受控经营数据。仅允许业务目录中登记的表、字段和关联关系。"

    def execute(self, input: ToolInput) -> ToolOutput:
        sql = input.parameters.get("sql")
        if not sql:
            return ToolOutput(
                success=False,
                error="缺少 sql 参数",
                error_code="sql_input_missing",
                repairable=False,
            )
        try:
            columns, rows = execute_readonly_sql(sql, allowed_tables=ALLOWED_TABLES)
            return ToolOutput(success=True, data={"columns": columns, "rows": rows})
        except ValueError as error:
            return ToolOutput(
                success=False,
                error=str(error),
                error_code="sql_validation_error",
                repairable=True,
            )
        except GroupingError:
            return ToolOutput(
                success=False,
                error="经营数据查询暂时无法完成。",
                error_code="sql_semantic_error",
                repairable=True,
            )
        except Exception:
            return ToolOutput(
                success=False,
                error="经营数据查询暂时无法完成。",
                error_code="business_db_execution_failed",
                repairable=False,
            )
