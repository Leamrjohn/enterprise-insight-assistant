"""Planner Agent —— 调用 LLM 生成受校验的工作流决策。"""

import logging

from app.core.exceptions import (
    PermanentModelError,
    RetryableModelError,
    StructuredOutputError,
)
from app.modules.analysis.agent_protocol import Agent, AgentInput, AgentOutput
from app.modules.analysis.planner.planning import PlanningService
from app.modules.analysis.tool_protocol import Tool

logger = logging.getLogger(__name__)


class PlannerAgent(Agent):
    """调用 LLM 生成工作流决策，但不生成最终业务结论。"""

    def __init__(self, planning_service: PlanningService | None = None) -> None:
        self._planning_service = planning_service

    @property
    def name(self) -> str:
        return "planner"

    @property
    def description(self) -> str:
        return "调用 LLM 分析用户问题并决定工作流动作和业务 Agent 路由"

    @property
    def allowed_tools(self) -> list[Tool]:
        return []  # Gateway 是模型适配层，不是业务 Tool

    def run(self, input: AgentInput) -> AgentOutput:
        if self._planning_service is None:
            self._planning_service = PlanningService()

        try:
            kwargs = {"conversation_context": input.context.get("conversation_context")}
            if input.context.get("feedback") is not None:
                kwargs["feedback"] = input.context["feedback"]
            if input.context.get("retry_context") is not None:
                kwargs["retry_context"] = input.context["retry_context"]
            if input.context.get("planner_memory"):
                kwargs["planner_memory"] = input.context["planner_memory"]
            if input.context.get("attachment_context"):
                kwargs["attachment_context"] = input.context["attachment_context"]
            decision = self._planning_service.decide(input.question, **kwargs)
        except RetryableModelError as error:
            logger.warning("Planner model retryable failure exhausted")
            return AgentOutput(
                success=False,
                attempts={"model_attempts": self._planning_service.model_attempts},
                error=f"无法生成 Planner 决策: {error}",
                error_code="planner_model_retryable_error",
                retryable=True,
            )
        except PermanentModelError as error:
            logger.error("Planner model permanent failure")
            return AgentOutput(
                success=False,
                attempts={"model_attempts": self._planning_service.model_attempts},
                error=f"无法生成 Planner 决策: {error}",
                error_code="planner_model_permanent_error",
            )
        except StructuredOutputError as error:
            logger.error("Planner structured-output validation failure")
            return AgentOutput(
                success=False,
                attempts={"model_attempts": self._planning_service.model_attempts},
                error=f"无法生成 Planner 决策: {error}",
                error_code="planner_invalid_output",
            )
        except Exception:
            logger.exception("Planner failed with an unexpected gateway error")
            return AgentOutput(
                success=False,
                attempts={"model_attempts": self._planning_service.model_attempts},
                error="Planner 服务发生未分类错误",
                error_code="planner_unexpected_error",
            )

        return AgentOutput(
            success=True,
            plan=decision.model_dump(),
            attempts={"model_attempts": self._planning_service.model_attempts},
        )
