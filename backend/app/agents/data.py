"""Data Agent —— 生成候选 SQL，并通过受控 SQL Tool 查询经营数据。"""

from app.agents.protocol import Agent, AgentInput, AgentOutput
from app.core.exceptions import (
    PermanentModelError,
    RetryableModelError,
    StructuredOutputError,
)
from app.services.sql_generation import SQLGenerationService
from app.tools.protocol import Tool, ToolInput
from app.tools.sql import SQLTool
from decimal import Decimal

MAX_DATA_ATTEMPTS = 2


def _make_json_safe(value):
    if isinstance(value, Decimal):
        return format(value, "f")

    if isinstance(value, (list, tuple)):
        return [_make_json_safe(item) for item in value]

    return value


class DataAgent(Agent):
    """只使用受控 SQL 生成服务和只读 SQL Tool 的 Agent。"""

    def __init__(
        self,
        sql_generator: SQLGenerationService | None = None,
        sql_tool: SQLTool | None = None,
    ) -> None:
        self._sql_generator = sql_generator
        self._sql_tool = sql_tool or SQLTool()

    @property
    def name(self) -> str:
        return "data"

    @property
    def description(self) -> str:
        return "生成受控候选 SQL，并查询经营数据库中的指标数据"

    @property
    def allowed_tools(self) -> list[Tool]:
        return [self._sql_tool]

    def run(self, input: AgentInput) -> AgentOutput:
        if self._sql_generator is None:
            self._sql_generator = SQLGenerationService()

        repair_reason = None
        previous_sql = None
        attempts = {
            "model_attempts": 0,
            "sql_attempts": 0,
        }

        for attempt_index in range(MAX_DATA_ATTEMPTS):
            try:
                attempts["model_attempts"] += 1
                candidate = self._sql_generator.generate(
                    input.question,
                    repair_reason=repair_reason,
                    previous_sql=previous_sql,
                )
            except PermanentModelError as error:
                return AgentOutput(
                    success=False,
                    attempts=attempts,
                    error=f"无法生成受控 SQL: {error}",
                    error_code="sql_generation_permanent_error",
                )
            except RetryableModelError:
                if attempt_index == MAX_DATA_ATTEMPTS - 1:
                    return AgentOutput(
                        success=False,
                        attempts=attempts,
                        error="经营数据 SQL 生成暂时无法完成。",
                        error_code="sql_generation_retryable_error",
                    )
                repair_reason = "sql_generation_retryable_error"
                previous_sql = None
                continue
            except StructuredOutputError:
                if attempt_index == MAX_DATA_ATTEMPTS - 1:
                    return AgentOutput(
                        success=False,
                        attempts=attempts,
                        error="经营数据 SQL 生成结果不符合要求。",
                        error_code="sql_generation_invalid_output",
                    )
                repair_reason = "sql_generation_invalid_output"
                previous_sql = None
                continue

            attempts["sql_attempts"] += 1
            result = self._sql_tool.execute(
                ToolInput(parameters={"sql": candidate.sql})
            )

            if result.success:
                return AgentOutput(
                    success=True,
                    answer=None,
                    attempts=attempts,
                    evidence=[
                        {
                            "sql": candidate.sql,
                            "purpose": candidate.purpose,
                            "columns": result.data.get("columns")
                            if result.data
                            else [],
                            "rows": _make_json_safe(
                                result.data.get("rows") if result.data else []
                            ),
                        }
                    ],
                )
            if result.repairable and attempt_index < MAX_DATA_ATTEMPTS - 1:
                repair_reason = result.error_code or "sql_validation_error"
                previous_sql = candidate.sql
                continue

            return AgentOutput(
                success=False,
                attempts=attempts,
                error=result.error or "经营数据查询失败。",
                error_code=result.error_code,
                evidence=[
                    {
                        "sql": candidate.sql,
                        "purpose": candidate.purpose,
                    }
                ],
            )
        return AgentOutput(
            success=False,
            attempts=attempts,
            error="经营数据查询未能完成。",
            error_code="data_attempt_budget_exhausted",
        )
