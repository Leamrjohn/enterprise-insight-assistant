"""T11e: a Planner whose model may look things up before it submits the plan.

The plan is the same PlannerDecision the fixed route asks for, now passed as the
arguments of submit_plan: the tool loop validates it, so a malformed plan goes
back to the model as a repairable error instead of a JSON repair prompt.  The
lookups are the planner's toolset (memory_search, report_search, report_export);
code still adds the selected memories to the prompt, so a plan that needs no
lookup costs one model call, as before.  Feedback and retries stay on the fixed
route, and a loop that ends without a plan falls back to it.
"""

from app.modules.analysis.agent_protocol import AgentInput, AgentOutput
from app.modules.analysis.planner.planner_agent import PlannerAgent, planning_kwargs
from app.modules.analysis.planner.planner_decision import PlannerDecision
from app.modules.analysis.planner.planning import (
    PlanningService,
    build_planning_system_prompt,
    finalize_decision,
)
from app.modules.analysis.tool_protocol import Toolset
from app.modules.runtime.model_governance import model_context_scope
from app.modules.runtime.tool_loop import LoopLimits, ToolReply, ToolSpec, run_tool_loop
from app.modules.runtime.tools.catalog import ANALYSIS_ROLES
from app.modules.runtime.tools.definition import ModelText, ToolDefinition
from app.modules.runtime.tools.direct import direct_tools

PLANNER_TOOL_CATALOG_VERSION = "planner-tools/v1"
PLANNER_TOOLS: tuple[ToolDefinition, ...] = (
    ToolDefinition(
        name="submit_plan",
        contract_version="submit_plan/v1",
        input_model=PlannerDecision,
        allowed_roles=ANALYSIS_ROLES,
        kind="control",
        model_text=ModelText(
            purpose="提交工作流决策，结束规划；参数就是要求输出的那份 JSON 决策。",
            when_to_use="已经能做决定时；不需要查询就直接提交。",
            when_not_to_use="决策依赖以前的结论或报告，而这些还没查到时。",
            example={
                "action": "analyze",
                "route": "data_only",
                "reason": "需要查询已交付订单销售额",
                "clarification_question": None,
                "response_message": None,
                "resolved_question": "2025年8月华东区已交付订单的销售额是多少",
            },
            common_errors=("把决策写在正文里而不是调用 submit_plan",),
        ),
    ),
)
PLANNER_TOOL_SPECS = [ToolSpec.from_definition(d) for d in PLANNER_TOOLS]
TOOL_LOOP_NOTE = (
    "\n本轮通过工具提交：把上面要求输出的 JSON 决策作为 submit_plan 的参数。"
    "决策需要以前的结论或报告时，可以先调用查询工具；查询结果只供参考，不是证据。"
)


class _PlanSession:
    def __init__(self, question: str) -> None:
        self.question = question
        self.plan: PlannerDecision | None = None

    def submit_plan(self, decision: PlannerDecision) -> ToolReply:
        """Keep the plan the fixed route would keep, then end the loop.

        decision has already passed PlannerDecision's own checks.  Give it the
        corrections every decision gets (finalize_decision with self.question),
        store the result in self.plan, and return ToolReply({"accepted": True},
        "finish") so the loop stops.
        """
        self.plan = finalize_decision(self.question, decision)
        return ToolReply({"accepted": True}, "finish")


class ToolCallingPlannerAgent(PlannerAgent):
    """Same output contract as PlannerAgent, so the workflow cannot tell."""

    def __init__(
        self,
        tools: Toolset,
        planning_service: PlanningService | None = None,
        limits: LoopLimits | None = None,
    ) -> None:
        super().__init__(planning_service)
        self._tools = tools
        self._limits = limits

    def run(self, input: AgentInput) -> AgentOutput:
        kwargs = planning_kwargs(input)
        if "feedback" in kwargs or "retry_context" in kwargs:
            return super().run(input)
        if self._planning_service is None:
            self._planning_service = PlanningService()
        prepared = self._planning_service.prepare(input.question, **kwargs)
        if isinstance(prepared, PlannerDecision):  # the context does not fit
            return AgentOutput(success=True, plan=prepared.model_dump())
        prompt, manifest = prepared
        session = _PlanSession(input.question)
        lookup_specs, lookup_handlers = direct_tools(self._tools)
        # The loop parses each call into its tool's own model before the handler.
        handlers: dict = {"submit_plan": session.submit_plan, **lookup_handlers}
        with model_context_scope(manifest):
            loop = run_tool_loop(
                self._planning_service.gateway,
                system_prompt=build_planning_system_prompt() + TOOL_LOOP_NOTE,
                user_prompt=prompt,
                specs=[*PLANNER_TOOL_SPECS, *lookup_specs],
                handlers=handlers,
                limits=self._limits,
            )
        tool_loop = {
            "catalog_version": PLANNER_TOOL_CATALOG_VERSION,
            "stop_reason": loop.stop_reason,
            "rounds": loop.rounds,
            "trace": loop.trace,
        }
        if session.plan is not None:
            return AgentOutput(
                success=True,
                plan=session.plan.model_dump(),
                attempts={"model_attempts": loop.rounds, "tool_loop": tool_loop},
            )
        # Lost its way without a plan: the fixed route plans this question.
        output = super().run(input)
        output.attempts = {
            **(output.attempts or {}),
            "tool_loop": tool_loop,
            "switched_to_fixed": loop.stop_reason,
        }
        return output
