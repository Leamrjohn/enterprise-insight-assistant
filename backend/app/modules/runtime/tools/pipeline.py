"""T3: the fixed order every tool call passes through.

Each stage either stops the call with an output (a denial, or the result of
running the tool) or returns None to let it continue.  The order is a contract:
a stage list that differs from STAGE_ORDER refuses to run, so no tool can skip a
check or run before one.  The stages themselves live in ToolRuntime.
"""

from collections.abc import Callable, Sequence
from typing import Any, TypeVar

STAGE_ORDER = (
    "allowlist",  # the task's frozen policy names this tool
    "current_authorization",  # the user is still an approved member with a role
    "input_schema",  # parameters match the registered input model
    "scope",  # company and frozen document scope
    "document_visibility",  # the documents are still visible to the user
    "server_parameters",  # policy-only controls the model cannot send
    "budget",  # reserve one call from the task's tool budget
    "execute",  # run the tool and write the audit record
)

CallT = TypeVar("CallT")
OutputT = TypeVar("OutputT")
Stage = Callable[[Any], Any]


class PipelineOrderError(RuntimeError):
    """The stage list is not STAGE_ORDER; a programming error, never a user one."""


def run(
    stages: Sequence[tuple[str, Callable[[CallT], OutputT | None]]], call: CallT
) -> OutputT:
    names = tuple(name for name, _ in stages)
    if names != STAGE_ORDER:
        raise PipelineOrderError(f"tool pipeline stages out of order: {names}")
    for _, stage in stages:
        output = stage(call)
        if output is not None:
            return output
    raise PipelineOrderError("tool pipeline ended without an output")
