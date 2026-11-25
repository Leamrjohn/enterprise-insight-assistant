"""Single execution boundary for workflow tools."""

import json
from dataclasses import dataclass, field, replace
from hashlib import sha256
from time import perf_counter

from app.core import tracing
from app.modules.analysis.tool_protocol import Tool, ToolInput, ToolOutput
from app.modules.documents.models import Documents
from app.modules.documents.repository import allowed_min_view_roles
from app.modules.identity.models import User
from app.modules.organizations.models import CompanyMember
from app.modules.runtime.model_governance import (
    ModelBudgetExceeded,
    ModelCallCancelled,
)
from app.modules.runtime.schemas import ToolBudget, ToolPolicy
from app.modules.runtime.tools import pipeline
from app.modules.runtime.tools.authorization import current_member_allowed
from app.modules.runtime.tools.errors import classify
from app.modules.runtime.tools.registry import default_registry
from app.modules.workflow.audit.events import append_workflow_event
from app.modules.workflow.audit.tool_call import ToolCallRecord
from app.modules.workflow.lifecycle.execution_attempt import TaskExecutionAttempt
from app.modules.workflow.models import AnalysisTask
from pydantic import ValidationError
from sqlalchemy.orm import Session

# Each denial tells the caller what to change; codes stay the machine contract.
DENY_MESSAGES = {
    "tool_not_allowlisted": "该工具不在本任务允许的工具列表中，请改用允许的工具。",
    "tool_schema_unregistered": "该工具没有登记参数契约，暂不可调用。",
    "tool_input_schema_invalid": "工具参数不符合契约：缺少必填项、类型错误或包含未定义参数。",
    "tool_budget_exhausted": "本任务的工具调用次数已用完，请基于已有结果作答或说明限制。",
    "tool_company_scope_missing": "调用缺少公司范围，请使用当前任务的公司。",
    "tool_company_scope_denied": "只能查询当前任务所属公司的数据。",
    "tool_current_authorization_denied": "当前用户已无权访问该公司数据。",
    "tool_document_scope_denied": "只能检索本任务冻结的文档范围。",
    "tool_document_current_authorization_denied": "部分文档已不再对当前用户可见。",
    "tool_task_missing": "任务记录不存在，无法继续调用工具。",
    "tool_unknown": "本任务没有登记这个工具，请改用已提供的工具。",
    "tool_output_contract_invalid": "工具返回的结果不符合契约，请稍后重试或说明限制。",
}
_GENERIC_DENY_MESSAGE = "工具调用不在已授权范围内。"


def deny_message(code: str) -> str:
    return DENY_MESSAGES.get(code, _GENERIC_DENY_MESSAGE)


@dataclass(frozen=True)
class ToolRuntimeContext:
    task_id: int
    company_id: int | None
    allowed_document_ids: frozenset[int]


@dataclass
class ToolCall:
    """One call as it moves through the pipeline; earlier stages fill later fields."""

    tool: Tool
    input: ToolInput
    policy: ToolPolicy | None = None
    requested_parameter_keys: list[str] = field(default_factory=list)


class ToolGateway:
    """T3: the only entry for a task's tool calls: call(name, parameters).

    Tools are registered once by name; every call then runs the same pipeline.
    """

    def __init__(self, runtime: "ToolRuntime") -> None:
        self._runtime = runtime
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        # A node that runs again registers a fresh instance under the same name.
        self._tools[tool.name] = tool

    def call(self, name: str, parameters: dict) -> ToolOutput:
        tool = self._tools.get(name)
        if tool is None:
            return ToolOutput(
                success=False,
                error=deny_message("tool_unknown"),
                error_code="tool_unknown",
            )
        input = ToolInput(parameters=parameters)
        empty_scope = self._runtime.resolve_empty_document_scope(tool, input)
        if empty_scope is not None:
            return empty_scope
        return self._runtime.execute(tool, input)


class RuntimeTool(Tool):
    """Adapter that preserves the existing Tool protocol for Agents."""

    def __init__(self, gateway: ToolGateway, tool: Tool) -> None:
        self._gateway = gateway
        self._tool = tool

    @property
    def name(self) -> str:
        return self._tool.name

    @property
    def description(self) -> str:
        return self._tool.description

    def execute(self, input: ToolInput) -> ToolOutput:
        return self._gateway.call(self._tool.name, input.parameters)


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
        self.gateway = ToolGateway(self)

    def wrap(self, tool: Tool) -> RuntimeTool:
        self.gateway.register(tool)
        return RuntimeTool(self.gateway, tool)

    def resolve_empty_document_scope(
        self, tool: Tool, input: ToolInput
    ) -> ToolOutput | None:
        """Resolve an authorized no-resource case without executing a search."""
        if tool.name != "rag_search" or input.parameters.get("document_ids") != []:
            return None
        policy = ToolPolicy.model_validate(self._task().tool_policy_snapshot)
        if tool.name not in policy.allowed_tools:
            return self._deny(tool, "tool_not_allowlisted", {})
        denied = self._validate_current_authorization(tool)
        if denied is not None:
            return denied
        validated = self._validate_input(tool, input)
        if isinstance(validated, ToolOutput):
            return validated
        if validated.parameters.get("company_id") != self._context.company_id:
            return self._deny(tool, "tool_company_scope_denied", {})
        if self._context.allowed_document_ids:
            return self._deny(tool, "tool_document_scope_denied", {})
        append_workflow_event(
            self._db,
            attempt=self._attempt,
            company_id=self._context.company_id,
            event_type="knowledge_scope_empty",
            node_name="knowledge",
            status="insufficient_evidence",
            details={"reason_code": "frozen_document_scope_empty"},
        )
        self._db.commit()
        return ToolOutput(
            success=True,
            data={
                "status": "insufficient_evidence",
                "answer": "当前任务没有可用的文档证据，未执行文档检索。",
                "evidences": [],
            },
            evidence=[],
        )

    @staticmethod
    def _tool_contract_version(tool: Tool) -> str:
        definition = default_registry().get(tool.name)
        return definition.contract_version if definition else f"{tool.name}/v1"

    def _deny(self, tool: Tool, code: str, details: dict) -> ToolOutput:
        details = {**details, "error_class": classify(code).value}
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
                tool_contract_version=self._tool_contract_version(tool),
                status="denied",
                error_code=code,
                metadata_json=details,
            )
        )
        self._db.commit()
        return ToolOutput(success=False, error=deny_message(code), error_code=code)

    def _validate_scope(
        self, tool: Tool, input: ToolInput, policy: ToolPolicy
    ) -> ToolOutput | None:
        if tool.name not in policy.allowed_tools:
            return self._deny(tool, "tool_not_allowlisted", {})
        if tool.name == "rag_search":
            if (
                policy.require_company_scope
                and input.parameters.get("company_id") != self._context.company_id
            ):
                return self._deny(tool, "tool_company_scope_denied", {})
            document_ids = input.parameters.get("document_ids")
            if policy.require_frozen_document_scope and (
                not self._context.allowed_document_ids
                or not isinstance(document_ids, list)
                or not set(document_ids).issubset(self._context.allowed_document_ids)
            ):
                return self._deny(tool, "tool_document_scope_denied", {})
        if (
            policy.require_company_scope
            and tool.name in {"sql_query", "template_query"}
            and self._context.company_id is None
        ):
            return self._deny(tool, "tool_company_scope_missing", {})
        return None

    def _validate_current_authorization(self, tool: Tool) -> ToolOutput | None:
        """Intersect frozen task scope with the initiator's current membership."""
        task = self._task()
        if self._context.company_id is None:
            return self._deny(tool, "tool_current_authorization_denied", {})
        definition = default_registry().get(tool.name)
        if not current_member_allowed(
            self._db,
            company_id=self._context.company_id,
            user_id=task.user_id,
            allowed_roles=definition.allowed_roles if definition else frozenset(),
        ):
            return self._deny(tool, "tool_current_authorization_denied", {})
        return None

    def _runtime_mcp_context(self, input: ToolInput) -> dict[str, object]:
        """Attach a Runtime-owned, request-specific binding for trusted MCP.

        The MCP server only validates and echoes this context.  It never decides
        authorization from it; Runtime has already enforced current membership,
        role and frozen scope before the request crosses the transport boundary.
        """
        task = self._task()
        user = self._db.get(User, task.user_id)
        membership = (
            self._db.query(CompanyMember)
            .filter(
                CompanyMember.company_id == self._context.company_id,
                CompanyMember.user_id == task.user_id,
            )
            .one_or_none()
        )
        if user is None or membership is None or self._context.company_id is None:
            raise RuntimeError("authorized MCP context disappeared")
        document_ids = input.parameters.get("document_ids")
        scope_payload = {
            "company_id": self._context.company_id,
            "document_ids": sorted(document_ids) if document_ids is not None else None,
        }
        scope_sha256 = sha256(
            json.dumps(scope_payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return {
            "version": "agent-evidence-runtime/v1",
            "tool_contract_version": "evidence_read/v1",
            "task_id": self._attempt.task_id,
            "execution_id": self._attempt.execution_id,
            "actor_id": task.user_id,
            "actor_auth_version": user.auth_version,
            "authorized_role": membership.role,
            "company_id": self._context.company_id,
            "document_scope_sha256": scope_sha256,
        }

    def _validate_current_document_scope(
        self, tool: Tool, input: ToolInput
    ) -> ToolOutput | None:
        """Require frozen RAG documents to remain visible to the initiator."""
        if tool.name != "rag_search":
            return None
        document_ids = input.parameters["document_ids"]
        task = self._task()
        membership = (
            self._db.query(CompanyMember)
            .filter(
                CompanyMember.company_id == self._context.company_id,
                CompanyMember.user_id == task.user_id,
            )
            .one_or_none()
        )
        if membership is None:
            return self._deny(tool, "tool_document_current_authorization_denied", {})
        visible_document_ids = {
            document_id
            for (document_id,) in (
                self._db.query(Documents.id)
                .filter(
                    Documents.id.in_(document_ids),
                    Documents.company_id == self._context.company_id,
                    Documents.min_view_role.in_(
                        allowed_min_view_roles(membership.role)
                    ),
                )
                .all()
            )
        }
        if not set(document_ids).issubset(visible_document_ids):
            return self._deny(tool, "tool_document_current_authorization_denied", {})
        return None

    def _validate_input(self, tool: Tool, input: ToolInput) -> ToolInput | ToolOutput:
        definition = default_registry().get(tool.name)
        if definition is None:
            return self._deny(
                tool,
                "tool_schema_unregistered",
                {"parameter_keys": sorted(input.parameters)},
            )
        try:
            return ToolInput(
                parameters=definition.input_model.model_validate(
                    input.parameters
                ).model_dump()
            )
        except ValidationError:
            return self._deny(
                tool,
                "tool_input_schema_invalid",
                {
                    "parameter_keys": sorted(input.parameters),
                    "schema": definition.contract_version,
                },
            )

    def _with_server_parameters(
        self, tool: Tool, input: ToolInput, policy: ToolPolicy
    ) -> ToolInput:
        """Attach policy-only controls after untrusted input was normalized."""
        if tool.name == "rag_search":
            return ToolInput(
                parameters={
                    **input.parameters,
                    "_runtime_database_timeout_ms": policy.rag_database_timeout_ms,
                    "_runtime_mcp_context": self._runtime_mcp_context(input),
                }
            )
        if tool.name != "sql_query":
            return input
        return ToolInput(
            parameters={
                **input.parameters,
                "_runtime_timeout_ms": policy.sql_statement_timeout_ms,
            }
        )

    @staticmethod
    def _with_evidence(tool: Tool, result: ToolOutput) -> ToolOutput:
        """Check a successful result against its contract and attach its Evidence."""
        definition = default_registry().get(tool.name)
        if definition is None or not (
            definition.output_model and definition.to_evidence
        ):
            return result
        try:
            output = definition.output_model.model_validate(result.data)
        except ValidationError:
            # A tool that broke its own contract is a defect, not the caller's error.
            return ToolOutput(
                success=False,
                error=deny_message("tool_output_contract_invalid"),
                error_code="tool_output_contract_invalid",
            )
        return replace(result, evidence=definition.to_evidence(output))

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
        with tracing.span(
            f"tool.{tool.name}",
            attributes={
                "tool.name": tool.name,
                "tool.version": getattr(tool, "version", None),
            },
        ) as current:
            output = self._execute(tool, input)
            tracing.set_attributes(
                current, {"tool.outcome": getattr(output, "outcome", None)}
            )
            return output

    def _execute(self, tool: Tool, input: ToolInput) -> ToolOutput:
        return pipeline.run(self._stages(), ToolCall(tool=tool, input=input))

    def _stages(self) -> list[tuple[str, pipeline.Stage]]:
        return [
            ("allowlist", self._stage_allowlist),
            ("current_authorization", self._stage_current_authorization),
            ("input_schema", self._stage_input_schema),
            ("scope", self._stage_scope),
            ("document_visibility", self._stage_document_visibility),
            ("server_parameters", self._stage_server_parameters),
            ("budget", self._stage_budget),
            ("execute", self._stage_execute),
        ]

    def _stage_allowlist(self, call: ToolCall) -> ToolOutput | None:
        call.policy = ToolPolicy.model_validate(self._task().tool_policy_snapshot)
        if call.tool.name not in call.policy.allowed_tools:
            return self._deny(call.tool, "tool_not_allowlisted", {})
        return None

    def _stage_current_authorization(self, call: ToolCall) -> ToolOutput | None:
        return self._validate_current_authorization(call.tool)

    def _stage_input_schema(self, call: ToolCall) -> ToolOutput | None:
        validated = self._validate_input(call.tool, call.input)
        if isinstance(validated, ToolOutput):
            return validated
        call.input = validated
        return None

    def _stage_scope(self, call: ToolCall) -> ToolOutput | None:
        assert call.policy is not None, "the allowlist stage loads the policy"
        return self._validate_scope(call.tool, call.input, call.policy)

    def _stage_document_visibility(self, call: ToolCall) -> ToolOutput | None:
        return self._validate_current_document_scope(call.tool, call.input)

    def _stage_server_parameters(self, call: ToolCall) -> ToolOutput | None:
        assert call.policy is not None, "the allowlist stage loads the policy"
        call.requested_parameter_keys = sorted(call.input.parameters)
        call.input = self._with_server_parameters(call.tool, call.input, call.policy)
        return None

    def _stage_budget(self, call: ToolCall) -> ToolOutput | None:
        return self._reserve_call(call.tool)

    def _stage_execute(self, call: ToolCall) -> ToolOutput:
        tool, input = call.tool, call.input
        append_workflow_event(
            self._db,
            attempt=self._attempt,
            company_id=self._context.company_id,
            event_type="tool_started",
            tool_name=tool.name,
            status="running",
            details={"parameter_keys": call.requested_parameter_keys},
        )
        self._db.commit()
        started = perf_counter()
        task_stop: ModelBudgetExceeded | ModelCallCancelled | None = None
        try:
            result = tool.execute(input)
            if not isinstance(result, ToolOutput):
                raise TypeError("tool returned an invalid result contract")
        except (ModelBudgetExceeded, ModelCallCancelled) as stop:
            # The whole task is stopping: keep the receipt, then let the signal through.
            task_stop = stop
            result = ToolOutput(
                success=False, error="任务已停止。", error_code=stop.code
            )
        except Exception:  # noqa: BLE001 - Persist a failed tool receipt without exception text.
            result = ToolOutput(
                success=False,
                error="工具执行暂时不可用。",
                error_code="tool_runtime_unexpected_error",
            )
        if result.success:
            result = self._with_evidence(tool, result)
        duration_ms = round((perf_counter() - started) * 1000)
        details: dict[str, object] = {"duration_ms": duration_ms}
        if result.success and isinstance(result.data, dict):
            rows = result.data.get("rows")
            if isinstance(rows, list):
                details["row_count"] = len(rows)
            details["result_status"] = result.data.get("status", "ready")
        if not result.success:
            details["error_class"] = classify(result.error_code).value
        append_workflow_event(
            self._db,
            attempt=self._attempt,
            company_id=self._context.company_id,
            event_type="tool_completed" if result.success else "tool_failed",
            tool_name=tool.name,
            status="succeeded" if result.success else "failed",
            error_code=result.error_code,
            details=details,
            duration_ms=duration_ms,
        )
        self._db.add(
            ToolCallRecord(
                task_id=self._attempt.task_id,
                execution_attempt_id=self._attempt.id,
                tool_name=tool.name,
                tool_contract_version=self._tool_contract_version(tool),
                status="succeeded" if result.success else "failed",
                error_code=result.error_code,
                duration_ms=duration_ms,
                metadata_json={
                    key: value for key, value in details.items() if key != "duration_ms"
                },
            )
        )
        self._db.commit()
        if task_stop is not None:
            raise task_stop
        return result
