"""SQL 数据查询工具"""

from app.modules.analysis.catalog.semantic_catalog import BUSINESS_TABLES
from app.modules.analysis.catalog.snapshot_catalog import SnapshotCatalog
from app.modules.analysis.data.sql_executor import execute_readonly_sql
from app.modules.analysis.tool_protocol import Tool, ToolInput, ToolOutput
from app.modules.organizations.models import BusinessDataSource
from psycopg.errors import GroupingError, QueryCanceled

ALLOWED_TABLES = set(BUSINESS_TABLES)
DEFAULT_STATEMENT_TIMEOUT_MS = 10_000


class SQLTool(Tool):
    """基于只读SQL查询经营数据的工具"""

    def __init__(
        self,
        *,
        data_source: BusinessDataSource | None = None,
        snapshot_catalog: SnapshotCatalog | None = None,
    ) -> None:
        if (data_source is None) != (snapshot_catalog is None):
            raise ValueError("公司数据源和 schema snapshot 必须同时提供")
        self._data_source = data_source
        self._snapshot_catalog = snapshot_catalog

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
        timeout_ms = input.parameters.get(
            "_runtime_timeout_ms", DEFAULT_STATEMENT_TIMEOUT_MS
        )
        if (
            not isinstance(timeout_ms, int)
            or isinstance(timeout_ms, bool)
            or not 100 <= timeout_ms <= 60_000
        ):
            return ToolOutput(
                success=False,
                error="SQL 执行超时策略不合法。",
                error_code="sql_timeout_policy_invalid",
                repairable=False,
            )
        try:
            if self._snapshot_catalog is None:
                columns, rows = execute_readonly_sql(
                    sql, allowed_tables=ALLOWED_TABLES, timeout_ms=timeout_ms
                )
            else:
                columns, rows = execute_readonly_sql(
                    sql,
                    allowed_tables=set(self._snapshot_catalog.tables),
                    catalog=self._snapshot_catalog,
                    data_source=self._data_source,
                    timeout_ms=timeout_ms,
                )
            return ToolOutput(success=True, data={"columns": columns, "rows": rows})
        except ValueError as error:
            return ToolOutput(
                success=False,
                error=str(error),
                error_code="sql_validation_error",
                repairable=True,
            )
        except QueryCanceled:
            return ToolOutput(
                success=False,
                error="经营数据查询超时。",
                error_code="sql_statement_timeout",
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
