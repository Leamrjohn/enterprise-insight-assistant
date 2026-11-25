"""T1: what the platform must know about a tool before it may run."""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

SideEffect = Literal["read", "write"]
# "in_process" calls the tool object directly; M1~M3 add MCP service names.
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
