"""A local MCP transport adapter for the existing read-only evidence tool."""

import asyncio
import json
import sys
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from app.core.settings import get_settings
from app.modules.analysis.tool_protocol import Tool, ToolInput, ToolOutput
from app.modules.knowledge.tool import RAGTool
from mcp import Client, StdioServerParameters
from mcp.server import MCPServer
from mcp_types import TextContent

MCP_SERVER_NAME = "agent-evidence"
MCP_SERVER_VERSION = "1.0.0"
MCP_TOOL_NAME = "evidence_read"
MCP_QUALIFIED_TOOL_NAME = f"{MCP_SERVER_NAME}:{MCP_TOOL_NAME}"
MCP_TOOL_CONTRACT_VERSION = "evidence_read/v1"
MCP_TRANSPORT = "stdio"
MCP_SDK_VERSION = "2.3.0"
MCP_RUNTIME_CONTEXT_VERSION = "agent-evidence-runtime/v1"
# A fresh local STDIO child must load the configured embedding model before its
# first read.  This is a bounded local cold-start budget, not an SLO.
MCP_STDIO_READ_TIMEOUT_SECONDS = 30
_RUNTIME_CONTEXT_KEYS = frozenset(
    {
        "version",
        "tool_contract_version",
        "task_id",
        "execution_id",
        "actor_id",
        "actor_auth_version",
        "authorized_role",
        "company_id",
        "document_scope_sha256",
    }
)
_AUTHORIZED_ROLES = frozenset({"owner", "admin", "analyst"})
_UNUSED_BUSINESS_DATABASE_PASSWORD = "evidence-mcp-does-not-access-business-db"
_MCP_INPUT_FIELDS = frozenset(
    {
        "company_id",
        "document_ids",
        "question",
        "runtime_database_timeout_ms",
        "runtime_request_context",
    }
)
_MCP_REQUIRED_INPUT_FIELDS = frozenset({"company_id", "document_ids", "question"})


def document_scope_sha256(company_id: int, document_ids: list[int] | None) -> str:
    """Create a stable scope binding without sending a second document list."""
    payload = {
        "company_id": company_id,
        "document_ids": sorted(document_ids) if document_ids is not None else None,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return sha256(encoded).hexdigest()


def runtime_context_sha256(context: dict[str, Any]) -> str:
    """Bind the MCP response to the Runtime-injected authorization context."""
    encoded = json.dumps(context, sort_keys=True, separators=(",", ":")).encode()
    return sha256(encoded).hexdigest()


def _is_valid_runtime_context(
    context: Any, *, company_id: int, document_ids: list[int] | None
) -> bool:
    if not isinstance(context, dict) or set(context) != _RUNTIME_CONTEXT_KEYS:
        return False
    if (
        context.get("version") != MCP_RUNTIME_CONTEXT_VERSION
        or context.get("tool_contract_version") != MCP_TOOL_CONTRACT_VERSION
        or context.get("company_id") != company_id
        or context.get("authorized_role") not in _AUTHORIZED_ROLES
        or context.get("document_scope_sha256")
        != document_scope_sha256(company_id, document_ids)
    ):
        return False
    return (
        all(
            isinstance(context.get(key), int) and not isinstance(context.get(key), bool)
            for key in ("task_id", "actor_id", "actor_auth_version", "company_id")
        )
        and isinstance(context.get("execution_id"), str)
        and bool(context["execution_id"].strip())
        and isinstance(context.get("document_scope_sha256"), str)
    )


def _is_compatible_catalog(catalog: Any) -> bool:
    """Require the one fixed capability and its bounded input contract."""
    if len(catalog.tools) != 1:
        return False
    tool = catalog.tools[0]
    if tool.name != MCP_TOOL_NAME or not isinstance(tool.input_schema, dict):
        return False
    properties = tool.input_schema.get("properties")
    required = tool.input_schema.get("required")
    return (
        isinstance(properties, dict)
        and frozenset(properties) == _MCP_INPUT_FIELDS
        and isinstance(required, list)
        and frozenset(required) == _MCP_REQUIRED_INPUT_FIELDS
    )


def _has_locked_mcp_sdk() -> bool:
    try:
        return version("mcp") == MCP_SDK_VERSION
    except PackageNotFoundError:
        return False


def _stdio_runtime_environment() -> dict[str, str]:
    """Pass only the configuration required by the read-only RAG subprocess."""
    settings = get_settings()
    return {
        "APP_ENV": settings.app_env,
        "LOG_LEVEL": settings.log_level,
        "DATABASE_HOST": settings.database_host,
        "DATABASE_PORT": str(settings.database_port),
        "DATABASE_NAME": settings.database_name,
        "DATABASE_USER": settings.database_user,
        "DATABASE_PASSWORD": settings.database_password.get_secret_value(),
        "DATABASE_ECHO": str(settings.database_echo).lower(),
        "DATABASE_POOL_SIZE": str(settings.database_pool_size),
        "DATABASE_MAX_OVERFLOW": str(settings.database_max_overflow),
        "DATABASE_POOL_TIMEOUT_SECONDS": str(settings.database_pool_timeout_seconds),
        # Settings validates this variable even though read-only RAG never opens
        # a business database connection.  Pass a non-credential sentinel so a
        # future accidental business-DB access fails instead of inheriting power.
        "BUSINESS_DATABASE_PASSWORD": _UNUSED_BUSINESS_DATABASE_PASSWORD,
        "RERANKER_MODEL": settings.reranker_model,
        "RAG_RETRIEVAL_TOP_K": str(settings.rag_retrieval_top_k),
        "RAG_RETRIEVAL_MIN_SCORE": str(settings.rag_retrieval_min_score),
        "RAG_RERANK_TOP_K": str(settings.rag_rerank_top_k),
        "RAG_RERANK_MIN_SCORE": str(settings.rag_rerank_min_score),
    }


def create_evidence_mcp_server(reader: Tool) -> MCPServer:
    """Expose one read-only tool; authorization remains with ToolRuntime."""
    server = MCPServer(MCP_SERVER_NAME, version=MCP_SERVER_VERSION)

    @server.tool(
        name=MCP_TOOL_NAME,
        description=(
            "Read evidence only from the caller's already-authorized frozen document "
            "scope. Use for document support; it cannot change data or permissions."
        ),
    )
    def evidence_read(
        company_id: int,
        document_ids: list[int] | None,
        question: str,
        runtime_database_timeout_ms: int = 10_000,
        runtime_request_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not _is_valid_runtime_context(
            runtime_request_context,
            company_id=company_id,
            document_ids=document_ids,
        ):
            return {"success": False, "error_code": "mcp_runtime_context_invalid"}
        result = reader.execute(
            ToolInput(
                parameters={
                    "company_id": company_id,
                    "document_ids": document_ids,
                    "question": question,
                    "_runtime_database_timeout_ms": runtime_database_timeout_ms,
                }
            )
        )
        if result.success:
            return {
                "success": True,
                "data": result.data,
                "runtime_context_sha256": runtime_context_sha256(
                    runtime_request_context
                ),
            }
        return {"success": False, "error_code": result.error_code}

    return server


class McpEvidenceReadTool(Tool):
    """Keep the local Tool contract while using a constrained MCP catalog."""

    def __init__(self, server: MCPServer | StdioServerParameters) -> None:
        self._server = server

    @classmethod
    def stdio(cls) -> "McpEvidenceReadTool":
        return cls(
            StdioServerParameters(
                command=sys.executable,
                args=["-m", "app.modules.knowledge.mcp_adapter"],
                env=_stdio_runtime_environment(),
            )
        )

    @property
    def name(self) -> str:
        return "rag_search"

    @property
    def description(self) -> str:
        return "通过受控 MCP 读取已授权文档中的证据。"

    def execute(self, input: ToolInput) -> ToolOutput:
        try:
            return asyncio.run(self._execute(input.parameters))
        except Exception:  # noqa: BLE001 - normalize every MCP transport failure
            return ToolOutput(
                success=False,
                error="证据读取暂时不可用。",
                error_code="mcp_transport_unavailable",
                repairable=True,
            )

    async def _execute(self, parameters: dict[str, Any]) -> ToolOutput:
        if not _has_locked_mcp_sdk():
            return ToolOutput(
                success=False,
                error="证据读取 SDK 版本不兼容。",
                error_code="mcp_sdk_version_mismatch",
            )
        company_id = parameters.get("company_id")
        document_ids = parameters.get("document_ids")
        runtime_context = parameters.get("_runtime_mcp_context")
        if not isinstance(company_id, int) or not _is_valid_runtime_context(
            runtime_context,
            company_id=company_id,
            document_ids=document_ids,
        ):
            return ToolOutput(
                success=False,
                error="证据读取请求缺少受控授权上下文。",
                error_code="mcp_runtime_context_invalid",
            )
        async with Client(
            self._server,
            raise_exceptions=False,
            read_timeout_seconds=MCP_STDIO_READ_TIMEOUT_SECONDS,
        ) as client:
            # Deliberately refresh on every request.  There is no directory
            # cache, so no cross-subject cache reuse or listChanged/TTL gap.
            catalog = await client.list_tools()
            if not _is_compatible_catalog(catalog):
                return ToolOutput(
                    success=False,
                    error="证据读取服务目录不兼容。",
                    error_code="mcp_catalog_mismatch",
                )
            result = await client.call_tool(
                MCP_TOOL_NAME,
                {
                    "company_id": company_id,
                    "document_ids": document_ids,
                    "question": parameters["question"],
                    "runtime_database_timeout_ms": parameters.get(
                        "_runtime_database_timeout_ms", 10_000
                    ),
                    "runtime_request_context": runtime_context,
                },
            )
        if result.result_type != "complete":
            return ToolOutput(
                success=False,
                error="证据读取要求未批准的补充输入。",
                error_code="mcp_input_required_not_supported",
            )
        if result.is_error or len(result.content) != 1:
            return ToolOutput(
                success=False,
                error="证据读取暂时不可用。",
                error_code="mcp_evidence_read_failed",
                repairable=True,
            )
        content = result.content[0]
        if not isinstance(content, TextContent):
            return ToolOutput(
                success=False,
                error="证据读取返回格式不合法。",
                error_code="mcp_evidence_read_malformed",
            )
        try:
            payload = json.loads(content.text)
        except json.JSONDecodeError:
            payload = None
        if not isinstance(payload, dict) or not isinstance(
            payload.get("success"), bool
        ):
            return ToolOutput(
                success=False,
                error="证据读取返回格式不合法。",
                error_code="mcp_evidence_read_malformed",
            )
        if payload["success"]:
            if payload.get("runtime_context_sha256") != runtime_context_sha256(
                runtime_context
            ):
                return ToolOutput(
                    success=False,
                    error="证据读取授权上下文校验失败。",
                    error_code="mcp_runtime_context_mismatch",
                )
            return ToolOutput(success=True, data=payload.get("data"))
        return ToolOutput(
            success=False,
            error="证据读取暂时不可用。",
            error_code="mcp_evidence_read_failed",
            repairable=True,
        )


def main() -> None:
    # STDIO protocol owns stdout; do not print or configure stdout logging here.
    create_evidence_mcp_server(RAGTool()).run(transport=MCP_TRANSPORT)


if __name__ == "__main__":
    main()
