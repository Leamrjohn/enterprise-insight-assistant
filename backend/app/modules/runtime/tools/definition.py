"""T1: what the platform must know about a tool before it may run."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel

if TYPE_CHECKING:
    from app.modules.runtime.tools.evidence import Evidence

SideEffect = Literal["read", "write"]
# T3c: runtime tools really execute; a capability is what a model calls, run by
# the runtime tool it is backed_by (or, without one, by code reading only what the
# task already holds); a control tool only ends a tool loop.
ToolKind = Literal["runtime", "capability", "control"]
OnOverflow = Literal["reject", "truncate_rows"]
# "in_process" runs the tool object inside the worker, for small fast tools;
# "mcp" runs it on the agent-tools service (M2b), which re-checks the signed context.
ALLOWED_TRANSPORTS = frozenset({"in_process", "mcp"})


@dataclass(frozen=True)
class ModelText:
    """T3b-2: what a model reads about a tool; rendered by ToolSpec.to_openai."""

    purpose: str
    when_to_use: str
    when_not_to_use: str
    example: dict[str, Any]
    common_errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    # "<name>/v<major>"; bump it whenever the input or output contract changes.
    contract_version: str
    input_model: type[BaseModel]
    allowed_roles: frozenset[str]
    side_effect: SideEffect = "read"
    transport: str = "in_process"
    kind: ToolKind = "runtime"
    backed_by: str | None = None
    # A successful result must match output_model; to_evidence turns the
    # validated result into the shared Evidence every node reads.
    output_model: type[BaseModel] | None = None
    to_evidence: "Callable[[Any], list[Evidence]] | None" = None
    # Required for capability and control tools: the model only knows them by it.
    model_text: ModelText | None = None
    # T5: how long the worker waits for one execution; None uses
    # tool_server_timeout_seconds.  An execution far past it writes an overrun event.
    timeout_ms: int | None = None
    # T5: a successful result larger than this is rejected, or for row results
    # cut to the rows that fit (truncate_rows) and marked truncated.
    max_result_tokens: int = 4_000
    on_overflow: OnOverflow = "reject"
