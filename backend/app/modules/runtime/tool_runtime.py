"""Single execution boundary for workflow tools."""

import json
from dataclasses import dataclass
from hashlib import sha256
from time import perf_counter

from app.modules.analysis.tool_protocol import Tool, ToolInput, ToolOutput
from app.modules.documents.models import Documents
from app.modules.documents.repository import allowed_min_view_roles
from app.modules.identity.models import User
from app.modules.organizations.models import CompanyMember
from app.modules.runtime.schemas import (
    RAGSearchInputSchema,
    SQLQueryInputSchema,
    TemplateQueryInputSchema,
    ToolBudget,
    ToolPolicy,
)
from app.modules.workflow.audit.events import append_workflow_event
from app.modules.workflow.lifecycle.execution_attempt import TaskExecutionAttempt
from app.modules.workflow.models import AnalysisTask
from app.modules.workflow.audit.tool_call import ToolCallRecord
from pydantic import ValidationError
from sqlalchemy.orm import Session

ANALYSIS_ROLES = frozenset({"owner", "admin", "analyst"})
TOOL_ALLOWED_ROLES = {
    "rag_search": ANALYSIS_ROLES,
    "sql_query": ANALYSIS_ROLES,
    "template_query": ANALYSIS_ROLES,
}


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

    @staticmethod
    def _tool_contract_version(tool: Tool) -> str:
        versions = {"rag_search": "rag_search/v2"}
        return versions.get(tool.name, f"{tool.name}/v1")

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
                tool_contract_version=self._tool_contract_version(tool),
                status="denied",
                error_code=code,
                metadata_json=details,
            )
        )
        self._db.commit()
        return ToolOutput(
            success=False, error="工具调用不在已授权范围内。", error_code=code
        )

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
        user = self._db.get(User, task.user_id)
        membership = (
            self._db.query(CompanyMember)
            .filter(
                CompanyMember.company_id == self._context.company_id,
                CompanyMember.user_id == task.user_id,
            )
            .one_or_none()
        )
        allowed_roles = TOOL_ALLOWED_ROLES.get(tool.name, frozenset())
        if (
            user is None
            or not user.is_active
            or membership is None
            or membership.status != "approved"
            or membership.role not in allowed_roles
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
        schemas = {
            "rag_search": RAGSearchInputSchema,
            "sql_query": SQLQueryInputSchema,
            "template_query": TemplateQueryInputSchema,
        }
        schema = schemas.get(tool.name)
        if schema is None:
            return self._deny(
                tool,
                "tool_schema_unregistered",
                {"parameter_keys": sorted(input.parameters)},
            )
        try:
            return ToolInput(
                parameters=schema.model_validate(input.parameters).model_dump()
            )
        except ValidationError:
            return self._deny(
                tool,
                "tool_input_schema_invalid",
                {
                    "parameter_keys": sorted(input.parameters),
                    "schema": f"{tool.name}/v1",
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
        policy = ToolPolicy.model_validate(self._task().tool_policy_snapshot)
        if tool.name not in policy.allowed_tools:
            return self._deny(tool, "tool_not_allowlisted", {})
        denied = self._validate_current_authorization(tool)
        if denied is not None:
            return denied
        validated = self._validate_input(tool, input)
        if isinstance(validated, ToolOutput):
            return validated
        input = validated
        denied = self._validate_scope(tool, input, policy)
        if denied is not None:
            return denied
        denied = self._validate_current_document_scope(tool, input)
        if denied is not None:
            return denied
        requested_parameter_keys = sorted(input.parameters)
        input = self._with_server_parameters(tool, input, policy)
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
            details={"parameter_keys": requested_parameter_keys},
        )
        self._db.commit()
        started = perf_counter()
        try:
            result = tool.execute(input)
            if not isinstance(result, ToolOutput):
                raise TypeError("tool returned an invalid result contract")
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
                tool_contract_version=self._tool_contract_version(tool),
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
