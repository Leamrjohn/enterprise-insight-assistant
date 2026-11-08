"""只执行仓库登记查询的经营数据工具。"""

from app.modules.analysis.data.data_request import DataRequest
from app.modules.analysis.data.query_registry import compile_business_query
from app.modules.analysis.data.sql_executor import execute_registered_readonly_query
from app.modules.analysis.tool_protocol import Tool, ToolInput, ToolOutput
from pydantic import ValidationError


class TemplateQueryTool(Tool):
    """把受校验的 query_id 和参数编译为仓库内固定 SQL。"""

    @property
    def name(self) -> str:
        return "template_query"

    @property
    def description(self) -> str:
        return "执行已登记的参数化经营查询，不接受原始 SQL。"

    def execute(self, input: ToolInput) -> ToolOutput:
        try:
            request = DataRequest.model_validate(input.parameters)
        except ValidationError:
            return ToolOutput(
                success=False,
                error="经营查询参数不合法。",
                error_code="template_query_invalid_request",
            )

        try:
            compiled = compile_business_query(request)
        except ValueError:
            return ToolOutput(
                success=False,
                error="当前经营查询暂未实现。",
                error_code="template_query_not_implemented",
            )

        try:
            columns, rows = execute_registered_readonly_query(
                compiled.sql,
                compiled.parameters,
            )
        except Exception:  # noqa: BLE001 - Keep driver details out of the tool response.
            return ToolOutput(
                success=False,
                error="经营数据查询暂时无法完成。",
                error_code="template_query_execution_failed",
            )

        return ToolOutput(
            success=True,
            data={
                "query_id": request.query_id,
                "parameters": request.model_dump(mode="json"),
                "columns": columns,
                "rows": rows,
            },
        )
