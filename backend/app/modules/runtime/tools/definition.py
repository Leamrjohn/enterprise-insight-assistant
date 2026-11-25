"""T1: what the platform must know about a tool before it may run."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel

if TYPE_CHECKING:
    from app.modules.runtime.tools.evidence import Evidence

SideEffect = Literal["read", "write"]
# T3c: runtime tools really execute; a capability is the model-facing face of
# the runtime tool it is backed_by; a control tool only ends a tool loop.
ToolKind = Literal["runtime", "capability", "control"]
# "in_process" calls the tool object directly; M2~M3 add the MCP transport.
ALLOWED_TRANSPORTS = frozenset({"in_process"})


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
