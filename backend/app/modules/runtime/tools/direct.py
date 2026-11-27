"""T11a: runtime tools a model calls by their own name, with no handler in an agent.

A runtime tool that declares model_text is shown to the model of every node whose
toolset holds it (workflow/orchestration/toolsets.py), so adding one never changes
an agent.  Its result only informs the model: report evidence still comes from
each node's own gated tools (run_sql, search_documents).
"""

from __future__ import annotations

import json
from typing import Any, Protocol

from app.modules.runtime.tool_guard import outcome_of_failure
from app.modules.runtime.tool_loop import Handler, ToolReply, ToolSpec
from app.modules.runtime.tools.registry import default_registry
from pydantic import BaseModel


class _Result(Protocol):
    """The fields of analysis.tool_protocol.ToolOutput read here."""

    success: bool
    data: Any
    error: str | None
    error_code: str | None
    repairable: bool
    model_feedback: str | None


class _Toolset(Protocol):
    """analysis.tool_protocol.Toolset; runtime sits below analysis and cannot import it."""

    def names(self) -> tuple[str, ...]: ...

    def call(self, name: str, parameters: dict[str, Any]) -> Any: ...


def direct_tools(toolset: _Toolset) -> tuple[list[ToolSpec], dict[str, Handler]]:
    """The specs and handlers for the toolset's tools a model may call directly."""
    registry = default_registry()
    specs: list[ToolSpec] = []
    handlers: dict[str, Handler] = {}
    for name in toolset.names():
        definition = registry.get(name)
        if (
            definition is None
            or definition.kind != "runtime"
            or definition.model_text is None
        ):
            continue
        specs.append(ToolSpec.from_definition(definition))
        handlers[name] = _handler(toolset, name)
    return specs, handlers


def _handler(toolset: _Toolset, name: str) -> Handler:
    def handle(arguments: BaseModel) -> ToolReply:
        parameters = arguments.model_dump(mode="json", exclude_none=True)
        return reply_for(toolset.call(name, parameters))

    return handle


def reply_for(result: _Result) -> ToolReply:
    """What the model sees of one call, and how it counts in the tool loop."""
    if result.success:
        # Plain JSON for the model: Decimal("0.10") becomes "0.10", a date its ISO text.
        return ToolReply({"result": json.loads(json.dumps(result.data, default=str))})
    outcome = outcome_of_failure(result)  # type: ignore[arg-type]
    # A hint helps only a call the model can repair; a denial shows just the error.
    detail = (
        result.model_feedback or result.error
        if outcome == "repairable"
        else result.error
    )
    return ToolReply({"error": detail}, outcome, result.error_code or "tool_failed")
