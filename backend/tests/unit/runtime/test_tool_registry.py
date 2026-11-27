from dataclasses import replace

import pytest
from app.modules.analysis.tool_protocol import ToolInput, ToolOutput
from app.modules.runtime.schemas import ToolPolicy
from app.modules.runtime.tool_runtime import ToolRuntime
from app.modules.runtime.tools import catalog
from app.modules.runtime.tools.definition import ToolDefinition
from app.modules.runtime.tools.registry import (
    ToolRegistry,
    ToolRegistryError,
    default_registry,
    validate_definitions,
)
from app.modules.workflow.models import AnalysisTask
from pydantic import BaseModel, ConfigDict


class _LookupInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str


FAKE = ToolDefinition(
    name="fake_lookup",
    contract_version="fake_lookup/v3",
    input_model=_LookupInput,
    allowed_roles=frozenset({"analyst"}),
    output_model=_LookupInput,
    to_evidence=lambda output: [],
)


class _Named:
    def __init__(self, name: str) -> None:
        self.name = name


@pytest.fixture
def fake_in_catalog(monkeypatch):
    """Simulate adding one tool to catalog.py and nothing else."""
    monkeypatch.setattr(catalog, "TOOLS", (*catalog.TOOLS, FAKE))
    default_registry.cache_clear()
    yield
    default_registry.cache_clear()


def test_real_catalog_is_valid_and_keeps_todays_order():
    assert validate_definitions(catalog.TOOLS) == []
    assert default_registry().names() == (
        "rag_search",
        "sql_query",
        "template_query",
        "metric_lookup",
        "dimension_list",
        "data_freshness",
        "doc_list",
        "doc_read",
    )


def test_new_tool_is_picked_up_everywhere_from_catalog_alone(fake_in_catalog):
    tool = _Named("fake_lookup")
    runtime = object.__new__(ToolRuntime)  # _validate_input needs no database

    assert default_registry().get("fake_lookup").allowed_roles == {"analyst"}
    assert ToolRuntime._tool_contract_version(tool) == "fake_lookup/v3"
    validated = runtime._validate_input(tool, ToolInput(parameters={"code": "A1"}))
    assert isinstance(validated, ToolInput)
    assert validated.parameters == {"code": "A1"}
    assert "fake_lookup" in ToolPolicy().allowed_tools
    default_policy = AnalysisTask.__table__.c.tool_policy_snapshot.default.arg(None)
    assert "fake_lookup" in default_policy["allowed_tools"]


def test_unregistered_tool_keeps_todays_fallbacks():
    tool = _Named("not_declared")

    assert default_registry().get("not_declared") is None
    assert ToolRuntime._tool_contract_version(tool) == "not_declared/v1"


@pytest.mark.parametrize(
    ("broken", "why"),
    [
        ((FAKE, replace(FAKE, contract_version="fake_lookup/v4")), "duplicate name"),
        ((replace(FAKE, side_effect="write"),), "write tool"),
        ((replace(FAKE, contract_version="fake_lookup/3"),), "bad version format"),
        ((replace(FAKE, contract_version="fake_lookup/v0"),), "version zero"),
        ((replace(FAKE, contract_version="other_tool/v1"),), "version of another"),
        ((replace(FAKE, transport="mcp_magic"),), "unknown transport"),
        ((replace(FAKE, allowed_roles=frozenset()),), "no roles"),
    ],
)
def test_each_broken_rule_stops_startup(broken, why):
    assert validate_definitions(broken), why
    with pytest.raises(ToolRegistryError):
        ToolRegistry(broken)


def test_every_problem_is_reported_not_only_the_first():
    broken = replace(FAKE, side_effect="write", allowed_roles=frozenset())

    assert len(validate_definitions((broken,))) == 2


def test_input_validation_denial_is_unchanged_for_unknown_tool():
    tool = _Named("not_declared")
    runtime = object.__new__(ToolRuntime)
    denials: list[str] = []
    runtime._deny = lambda tool, code, details: (
        denials.append(code)
        or ToolOutput(  # type: ignore[method-assign]
            success=False, error_code=code
        )
    )

    runtime._validate_input(tool, ToolInput(parameters={}))

    assert denials == ["tool_schema_unregistered"]
