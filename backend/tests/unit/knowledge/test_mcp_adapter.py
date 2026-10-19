"""MCP transport contracts for the existing read-only evidence capability."""

import asyncio
import sys

from app.core.settings import get_settings
from app.modules.analysis.tool_protocol import Tool, ToolInput, ToolOutput
from app.modules.knowledge.mcp_adapter import (
    MCP_RUNTIME_CONTEXT_VERSION,
    MCP_TOOL_CONTRACT_VERSION,
    MCP_TOOL_NAME,
    McpEvidenceReadTool,
    create_evidence_mcp_server,
    document_scope_sha256,
)
from mcp import Client, StdioServerParameters
from mcp.server import MCPServer
from mcp_types import CallToolResult, ResourceLink, TextContent


class _Reader(Tool):
    def __init__(self, result: ToolOutput) -> None:
        self.result = result
        self.inputs: list[ToolInput] = []

    @property
    def name(self) -> str:
        return "reader"

    @property
    def description(self) -> str:
        return "test reader"

    def execute(self, input: ToolInput) -> ToolOutput:
        self.inputs.append(input)
        return self.result


def _input() -> ToolInput:
    return ToolInput(
        parameters={
            "company_id": 7,
            "document_ids": [11],
            "question": "what supports this?",
            "_runtime_database_timeout_ms": 321,
            "_runtime_mcp_context": {
                "version": MCP_RUNTIME_CONTEXT_VERSION,
                "tool_contract_version": MCP_TOOL_CONTRACT_VERSION,
                "task_id": 17,
                "execution_id": "test-execution",
                "actor_id": 19,
                "actor_auth_version": 0,
                "authorized_role": "analyst",
                "company_id": 7,
                "document_scope_sha256": document_scope_sha256(7, [11]),
            },
        }
    )


def test_mcp_evidence_read_preserves_the_local_tool_result() -> None:
    reader = _Reader(ToolOutput(success=True, data={"status": "ready", "rows": []}))

    result = McpEvidenceReadTool(create_evidence_mcp_server(reader)).execute(_input())

    assert result == ToolOutput(success=True, data={"status": "ready", "rows": []})
    assert reader.inputs == [
        ToolInput(
            parameters={
                "company_id": 7,
                "document_ids": [11],
                "question": "what supports this?",
                "_runtime_database_timeout_ms": 321,
            }
        )
    ]


def test_mcp_evidence_read_normalizes_reader_failure() -> None:
    reader = _Reader(
        ToolOutput(success=False, error="internal detail", error_code="reader_failed")
    )

    result = McpEvidenceReadTool(create_evidence_mcp_server(reader)).execute(_input())

    assert result.success is False
    assert result.error_code == "mcp_evidence_read_failed"
    assert result.repairable is True
    assert "internal detail" not in (result.error or "")


def test_mcp_evidence_read_rejects_catalog_drift() -> None:
    server = MCPServer("wrong-server", version="1")

    @server.tool(name="wrong_tool")
    def wrong_tool() -> dict:
        return {"success": True}

    result = McpEvidenceReadTool(server).execute(_input())

    assert result.success is False
    assert result.error_code == "mcp_catalog_mismatch"


def test_mcp_evidence_read_rejects_malformed_server_result() -> None:
    server = MCPServer("malformed-server", version="1")

    @server.tool(name=MCP_TOOL_NAME)
    def evidence_read(
        company_id: int,
        document_ids: list[int] | None,
        question: str,
        runtime_database_timeout_ms: int = 10_000,
        runtime_request_context: dict | None = None,
    ) -> str:
        del (
            company_id,
            document_ids,
            question,
            runtime_database_timeout_ms,
            runtime_request_context,
        )
        return "not JSON"

    result = McpEvidenceReadTool(server).execute(_input())

    assert result.success is False
    assert result.error_code == "mcp_evidence_read_malformed"


def test_mcp_evidence_read_rejects_resource_link_result() -> None:
    server = MCPServer("resource-link-server", version="1")

    @server.tool(name=MCP_TOOL_NAME)
    def evidence_read(
        company_id: int,
        document_ids: list[int] | None,
        question: str,
        runtime_database_timeout_ms: int = 10_000,
        runtime_request_context: dict | None = None,
    ) -> CallToolResult:
        del (
            company_id,
            document_ids,
            question,
            runtime_database_timeout_ms,
            runtime_request_context,
        )
        return CallToolResult(
            content=[
                ResourceLink(
                    name="unapproved-resource",
                    uri="https://example.invalid/evidence",
                )
            ]
        )

    result = McpEvidenceReadTool(server).execute(_input())

    assert result.success is False
    assert result.error_code == "mcp_evidence_read_malformed"


def test_mcp_evidence_read_rejects_input_required_extension() -> None:
    server = MCPServer("input-required-server", version="1")

    @server.tool(name=MCP_TOOL_NAME)
    def evidence_read(
        company_id: int,
        document_ids: list[int] | None,
        question: str,
        runtime_database_timeout_ms: int = 10_000,
        runtime_request_context: dict | None = None,
    ) -> CallToolResult:
        del (
            company_id,
            document_ids,
            question,
            runtime_database_timeout_ms,
            runtime_request_context,
        )
        return CallToolResult(
            content=[TextContent(type="text", text='{"success": true, "data": {}}')],
            resultType="input_required",
        )

    result = McpEvidenceReadTool(server).execute(_input())

    assert result.success is False
    assert result.error_code == "mcp_input_required_not_supported"


def test_mcp_evidence_read_handles_disconnected_stdio_server() -> None:
    result = McpEvidenceReadTool(
        StdioServerParameters(command=sys.executable, args=["-c", "pass"])
    ).execute(_input())

    assert result.success is False
    assert result.error_code == "mcp_transport_unavailable"


def test_mcp_evidence_read_rejects_missing_runtime_authorization_context() -> None:
    reader = _Reader(ToolOutput(success=True, data={}))
    request = _input()
    request.parameters.pop("_runtime_mcp_context")

    result = McpEvidenceReadTool(create_evidence_mcp_server(reader)).execute(request)

    assert result.success is False
    assert result.error_code == "mcp_runtime_context_invalid"
    assert reader.inputs == []


def test_mcp_evidence_read_rejects_context_receipt_mismatch() -> None:
    server = MCPServer("wrong-context-receipt", version="1")

    @server.tool(name=MCP_TOOL_NAME)
    def evidence_read(
        company_id: int,
        document_ids: list[int] | None,
        question: str,
        runtime_database_timeout_ms: int = 10_000,
        runtime_request_context: dict | None = None,
    ) -> dict:
        del (
            company_id,
            document_ids,
            question,
            runtime_database_timeout_ms,
            runtime_request_context,
        )
        return {
            "success": True,
            "data": {"status": "ready"},
            "runtime_context_sha256": "not-the-request-context",
        }

    result = McpEvidenceReadTool(server).execute(_input())

    assert result.success is False
    assert result.error_code == "mcp_runtime_context_mismatch"


def test_stdio_server_allows_only_read_only_rag_runtime_configuration() -> None:
    tool = McpEvidenceReadTool.stdio()

    assert isinstance(tool._server, StdioServerParameters)
    assert set(tool._server.env or {}) == {
        "APP_ENV",
        "LOG_LEVEL",
        "DATABASE_HOST",
        "DATABASE_PORT",
        "DATABASE_NAME",
        "DATABASE_USER",
        "DATABASE_PASSWORD",
        "DATABASE_ECHO",
        "DATABASE_POOL_SIZE",
        "DATABASE_MAX_OVERFLOW",
        "DATABASE_POOL_TIMEOUT_SECONDS",
        "BUSINESS_DATABASE_PASSWORD",
        "RERANKER_MODEL",
        "RAG_RETRIEVAL_TOP_K",
        "RAG_RETRIEVAL_MIN_SCORE",
        "RAG_RERANK_TOP_K",
        "RAG_RERANK_MIN_SCORE",
    }
    assert "INPUT_ARTIFACT_OBJECT_STORAGE_SECRET_ACCESS_KEY" not in tool._server.env
    assert "OPENAI_API_KEY" not in tool._server.env
    assert "DEEPSEEK_API_KEY" not in tool._server.env
    assert tool._server.env["BUSINESS_DATABASE_PASSWORD"] != (
        get_settings().business_database_password.get_secret_value()
    )


def test_stdio_server_exposes_only_evidence_read() -> None:
    async def list_tool_names() -> list[str]:
        parameters = McpEvidenceReadTool.stdio()._server
        assert isinstance(parameters, StdioServerParameters)
        async with Client(parameters) as client:
            catalog = await client.list_tools()
        return [tool.name for tool in catalog.tools]

    assert asyncio.run(list_tool_names()) == [MCP_TOOL_NAME]
