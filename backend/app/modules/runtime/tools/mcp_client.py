"""M1: call one tool on the agent-tools service with a signed runtime context.

Every way the service can fail to answer becomes mcp_transport_unavailable
within the timeout, so the breaker and the loop see one clear infra_error.
"""

import asyncio
import json
from dataclasses import asdict, dataclass
from typing import Any

from app.modules.runtime.tools.context import RuntimeContext, sign
from app.modules.runtime.tools.wire import decode
from mcp import Client
from mcp.server import MCPServer
from mcp_types import TextContent


@dataclass(frozen=True)
class ServiceReply:
    """What the service answered; each tool adapter turns it into its own output."""

    success: bool
    data: Any = None
    error_code: str | None = None
    # M3: what a SQL repair needs; the tool already kept other companies out of it.
    error: str | None = None
    repairable: bool = False
    model_feedback: str | None = None


_UNAVAILABLE = ServiceReply(success=False, error_code="mcp_transport_unavailable")
_MALFORMED = ServiceReply(success=False, error_code="mcp_response_malformed")


def call_tool(
    server: str | MCPServer,
    name: str,
    arguments: dict[str, Any],
    context: RuntimeContext,
    *,
    key: bytes,
    timeout_seconds: float,
) -> ServiceReply:
    """server is the service URL, or an in-process MCPServer in tests."""
    try:
        return asyncio.run(
            asyncio.wait_for(
                _call(server, name, arguments, context, key, timeout_seconds),
                timeout=timeout_seconds,
            )
        )
    except Exception:  # noqa: BLE001 - every transport failure is one outage
        return _UNAVAILABLE


async def _call(
    server: str | MCPServer,
    name: str,
    arguments: dict[str, Any],
    context: RuntimeContext,
    key: bytes,
    timeout_seconds: float,
) -> ServiceReply:
    async with Client(
        server, raise_exceptions=False, read_timeout_seconds=timeout_seconds
    ) as client:
        result = await client.call_tool(
            name,
            {
                "arguments": arguments,
                "context": asdict(context),
                "signature": sign(context, key),
            },
        )
    if result.is_error or len(result.content) != 1:
        return _UNAVAILABLE
    content = result.content[0]
    if not isinstance(content, TextContent):
        return _MALFORMED
    try:
        payload = json.loads(content.text)
    except json.JSONDecodeError:
        return _MALFORMED
    if not isinstance(payload, dict) or not isinstance(payload.get("success"), bool):
        return _MALFORMED
    if payload["success"]:
        try:
            return ServiceReply(success=True, data=decode(payload.get("data")))
        except (KeyError, TypeError, ValueError):
            return _MALFORMED
    code = payload.get("error_code")
    error = payload.get("error")
    feedback = payload.get("model_feedback")
    if (
        not isinstance(code, str)
        or not isinstance(error, str | None)
        or not isinstance(feedback, str | None)
    ):
        return _MALFORMED
    return ServiceReply(
        success=False,
        error_code=code,
        error=error,
        repairable=payload.get("repairable") is True,
        model_feedback=feedback,
    )
