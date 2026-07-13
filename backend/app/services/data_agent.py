"""Data Agent —— 基于经营数据回答问题的 Agent"""

from app.services.agent_protocol import Agent, AgentInput, AgentOutput
from app.services.tool_protocol import Tool, ToolInput
from app.services.sql_tool import SQLTool


class DataAgent(Agent):
    """只使用只读SQL工具的 Agent"""

    def __init__(self):
        self._sql_tool = SQLTool()

    @property
    def name(self) -> str:
        return "data"

    @property
    def description(self) -> str:
        return "使用SQL查询经营数据库，回答数据分析和指标计算问题"

    @property
    def allowed_tools(self) -> list[Tool]:
        return [self._sql_tool]

    def run(self, input: AgentInput) -> AgentOutput:
        """执行数据查询——注意：这个 Agent 需要上层 Planner 告诉它查什么 SQL"""
        sql = input.context.get("sql", "")
        if not sql:
            return AgentOutput(
                success=False,
                error="DataAgent 需要 context.sql —— 请由 Planner 先生成 SQL",
            )

        tool_input = ToolInput(parameters={"sql": sql})
        result = self._sql_tool.execute(tool_input)

        if not result.success:
            return AgentOutput(success=False, error=result.error)

        return AgentOutput(
            success=True,
            answer=None,
            evidence=[{
                "columns": result.data.get("columns") if result.data else [],
                "rows": result.data.get("rows") if result.data else [],
            }],
        )
