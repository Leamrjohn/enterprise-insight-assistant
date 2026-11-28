"""T1: load the catalog once and refuse to start on a bad declaration."""

import re
from collections.abc import Iterable
from functools import lru_cache

from app.modules.runtime.tools.definition import ALLOWED_TRANSPORTS, ToolDefinition

_CONTRACT_VERSION = re.compile(r"^(?P<name>[a-z_]+)/v[1-9][0-9]*$")
_SCOPE_FIELDS = frozenset({"company_id", "document_ids"})


class ToolRegistryError(ValueError):
    """A catalog declaration breaks a platform rule; the process must not start."""


def validate_definitions(definitions: Iterable[ToolDefinition]) -> list[str]:
    """Return one readable problem per broken rule; an empty list means valid.

    Rules (all must hold):
    1. names are unique;
    2. side_effect is "read" (no write tools are open yet);
    3. contract_version matches _CONTRACT_VERSION and its name part equals name;
    4. transport is in ALLOWED_TRANSPORTS;
    5. allowed_roles is not empty;
    6. a runtime tool declares output_model and to_evidence, and no backed_by;
    7. a capability's backed_by, when set, is a declared runtime tool;
    8. a control tool has no backed_by;
    9. capability and control tools carry model_text;
    10. a runtime tool with model_text, which the model calls directly (T11a),
        takes no scope field: the company and documents come from the context.
    11. timeout_ms, when set, and max_result_tokens are positive (T5).
    """
    definitions = tuple(definitions)
    kinds = {definition.name: definition.kind for definition in definitions}
    problems: list[str] = []
    seen: set[str] = set()
    for definition in definitions:
        name = definition.name
        if name in seen:
            problems.append(f"{name}: declared more than once")
        seen.add(name)
        if definition.side_effect != "read":
            problems.append(f"{name}: side_effect must be read")
        match = _CONTRACT_VERSION.match(definition.contract_version)
        if match is None:
            problems.append(
                f"{name}: contract_version {definition.contract_version!r} "
                "must look like name/vN"
            )
        elif match.group("name") != name:
            problems.append(
                f"{name}: contract_version {definition.contract_version!r} "
                "names another tool"
            )
        if definition.transport not in ALLOWED_TRANSPORTS:
            problems.append(f"{name}: unknown transport {definition.transport!r}")
        if not definition.allowed_roles:
            problems.append(f"{name}: allowed_roles is empty")
        if definition.kind == "runtime":
            if definition.output_model is None or definition.to_evidence is None:
                problems.append(
                    f"{name}: a runtime tool needs output_model and to_evidence"
                )
            if definition.backed_by is not None:
                problems.append(f"{name}: a runtime tool runs itself, not backed_by")
        elif definition.kind == "capability":
            if (
                definition.backed_by is not None
                and kinds.get(definition.backed_by) != "runtime"
            ):
                problems.append(
                    f"{name}: backed_by {definition.backed_by!r} is not a runtime tool"
                )
        elif definition.backed_by is not None:
            problems.append(f"{name}: a control tool has no backed_by")
        if definition.kind != "runtime" and definition.model_text is None:
            problems.append(f"{name}: a {definition.kind} tool needs model_text")
        if definition.kind == "runtime" and definition.model_text is not None:
            scope = sorted(_SCOPE_FIELDS & set(definition.input_model.model_fields))
            if scope:
                problems.append(f"{name}: the model must not set {', '.join(scope)}")
        if (definition.timeout_ms is not None and definition.timeout_ms <= 0) or (
            definition.max_result_tokens <= 0
        ):
            problems.append(
                f"{name}: timeout_ms and max_result_tokens must be positive"
            )
    return problems


class ToolRegistry:
    def __init__(self, definitions: Iterable[ToolDefinition]) -> None:
        definitions = tuple(definitions)
        problems = validate_definitions(definitions)
        if problems:
            raise ToolRegistryError("; ".join(problems))
        self._by_name = {definition.name: definition for definition in definitions}

    def get(self, name: str) -> ToolDefinition | None:
        return self._by_name.get(name)

    def names(self) -> tuple[str, ...]:
        """Declared order, which is also the default task allowlist order."""
        return tuple(self._by_name)


@lru_cache(maxsize=1)
def default_registry() -> ToolRegistry:
    from app.modules.runtime.tools.catalog import TOOLS

    return ToolRegistry(TOOLS)
