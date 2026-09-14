"""Single execution boundary for workflow tools."""

from dataclasses import dataclass
from time import perf_counter

from sqlalchemy.orm import Session

from app.modules.workflow.models import AnalysisTask
from app.modules.workflow.execution_attempt import TaskExecutionAttempt
from app.modules.workflow.tool_call import ToolCallRecord
from app.modules.runtime.schemas import ToolBudget, ToolPolicy
from app.modules.workflow.events import append_workflow_event
from app.modules.analysis.tool_protocol import Tool, ToolInput, ToolOutput


@dataclass(frozen=True)
class ToolRuntimeContext:
    task_id: int
    company_id: int | None
    allowed_document_ids: frozenset[int]


class RuntimeTool(Tool):
    """Adapter that preserves the existing Tool protocol for Agents."""

    def __init__(self, runtime: "ToolRuntime", tool: Tool) -> None:
        self._runtime = runtime
        self._tool = tool

    @property
    def name(self) -> str:
        return self._tool.name

    @property
    def description(self) -> str:
        return self._tool.description

    def execute(self, input: ToolInput) -> ToolOutput:
        return self._runtime.execute(self._tool, input)


class ToolRuntime:
    """Enforce frozen scope and emit a redacted audit trail around every Tool."""

    def __init__(
        self,
        *,
        db: Session,
        attempt: TaskExecutionAttempt,
        context: ToolRuntimeContext,
    ) -> None:
        if context.task_id != attempt.task_id:
            raise ValueError("tool runtime task scope does not match execution attempt")
        self._db = db
        self._attempt = attempt
        self._context = context

    def wrap(self, tool: Tool) -> RuntimeTool:
        return RuntimeTool(self, tool)

    def _deny(self, tool: Tool, code: str, details: dict) -> ToolOutput:
        append_workflow_event(
            self._db,
            attempt=self._attempt,
            company_id=self._context.company_id,
            event_type="tool_denied",
            tool_name=tool.name,
            status="denied",
            error_code=code,
            details=details,
        )
        self._db.add(
            ToolCallRecord(
                task_id=self._attempt.task_id,
                execution_attempt_id=self._attempt.id,
                tool_name=tool.name,
                status="denied",
                error_code=code,
                metadata_json=details,
            )
        )
        self._db.commit()
        return ToolOutput(
            success=False, error="工具调用不在已授权范围内。", error_code=code
        )

    def _validate_scope(self, tool: Tool, input: ToolInput) -> ToolOutput | None:
        policy = ToolPolicy.model_validate(self._task().tool_policy_snapshot)
        if tool.name not in policy.allowed_tools:
            return self._deny(tool, "tool_not_allowlisted", {})
        if tool.name == "rag_search":
            if (
                policy.require_company_scope
                and input.parameters.get("company_id") != self._context.company_id
            ):
                return self._deny(tool, "tool_company_scope_denied", {})
            document_ids = input.parameters.get("document_ids")
            if (
                policy.require_frozen_document_scope
                and document_ids is not None
                and (
                    not isinstance(document_ids, list)
                    or not set(document_ids).issubset(
                        self._context.allowed_document_ids
                    )
                )
            ):
                return self._deny(tool, "tool_document_scope_denied", {})
        if (
            policy.require_company_scope
            and tool.name in {"sql_query", "template_query"}
            and self._context.company_id is None
        ):
            return self._deny(tool, "tool_company_scope_missing", {})
        return None

    def _task(self) -> AnalysisTask:
        task = self._db.get(AnalysisTask, self._attempt.task_id)
        if task is None:
            raise RuntimeError("tool runtime task disappeared")
        return task

    def _reserve_call(self, tool: Tool) -> ToolOutput | None:
        task = self._db.get(AnalysisTask, self._attempt.task_id, with_for_update=True)
        if task is None:
            return self._deny(tool, "tool_task_missing", {})
        budget = ToolBudget.model_validate(task.tool_budget_snapshot)
        usage = dict(task.tool_budget_usage or {})
        calls_by_tool = dict(usage.get("calls_by_tool") or {})
        calls = int(usage.get("calls", 0))
        tool_calls = int(calls_by_tool.get(tool.name, 0))
        if calls >= budget.max_calls or tool_calls >= budget.max_calls_per_tool:
            return self._deny(tool, "tool_budget_exhausted", {})
        calls_by_tool[tool.name] = tool_calls + 1
        task.tool_budget_usage = {"calls": calls + 1, "calls_by_tool": calls_by_tool}
        self._db.commit()
        return None

    def execute(self, tool: Tool, input: ToolInput) -> ToolOutput:
        denied = self._validate_scope(tool, input)
        if denied is not None:
            return denied
        exhausted = self._reserve_call(tool)
        if exhausted is not None:
            return exhausted

        append_workflow_event(
            self._db,
            attempt=self._attempt,
            company_id=self._context.company_id,
            event_type="tool_started",
            tool_name=tool.name,
            status="running",
            details={"parameter_keys": sorted(input.parameters)},
        )
        self._db.commit()
        started = perf_counter()
        try:
            result = tool.execute(input)
        except Exception:
            result = ToolOutput(
                success=False,
                error="工具执行暂时不可用。",
                error_code="tool_runtime_unexpected_error",
            )
        details = {"duration_ms": round((perf_counter() - started) * 1000)}
        if result.success and isinstance(result.data, dict):
            rows = result.data.get("rows")
            if isinstance(rows, list):
                details["row_count"] = len(rows)
            details["result_status"] = result.data.get("status", "ready")
        append_workflow_event(
            self._db,
            attempt=self._attempt,
            company_id=self._context.company_id,
            event_type="tool_completed" if result.success else "tool_failed",
            tool_name=tool.name,
            status="succeeded" if result.success else "failed",
            error_code=result.error_code,
            details=details,
            duration_ms=details["duration_ms"],
        )
        self._db.add(
            ToolCallRecord(
                task_id=self._attempt.task_id,
                execution_attempt_id=self._attempt.id,
                tool_name=tool.name,
                status="succeeded" if result.success else "failed",
                error_code=result.error_code,
                duration_ms=details["duration_ms"],
                metadata_json={
                    key: value for key, value in details.items() if key != "duration_ms"
                },
            )
        )
        self._db.commit()
        return result
