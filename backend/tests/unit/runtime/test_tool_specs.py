import json
from dataclasses import replace
from pathlib import Path

import pytest
from app.modules.analysis.data.tool_agent import DATA_TOOL_SPECS, DATA_TOOLS
from app.modules.knowledge.tool_agent import KNOWLEDGE_TOOL_SPECS, KNOWLEDGE_TOOLS
from app.modules.runtime.tool_loop import ToolSpec
from app.modules.runtime.tools import catalog
from app.modules.runtime.tools.definition import ModelText
from app.modules.runtime.tools.registry import validate_definitions
from app.modules.workflow.orchestration.toolsets import tool_catalog

SNAPSHOT = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "tool_specs"
    / "model_visible_v1.json"
)


def test_the_model_reads_word_for_word_what_it_read_before_t3b2():
    # Recorded from the hand-written ToolSpecs just before they moved into the registry.
    expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))

    assert [spec.to_openai() for spec in DATA_TOOL_SPECS] == expected["data"]
    assert [spec.to_openai() for spec in KNOWLEDGE_TOOL_SPECS] == expected["knowledge"]
    assert [spec.version for spec in DATA_TOOL_SPECS] == expected["versions"]["data"]
    assert [spec.version for spec in KNOWLEDGE_TOOL_SPECS] == (
        expected["versions"]["knowledge"]
    )


def test_every_model_facing_tool_is_in_the_one_registry():
    registry = tool_catalog()

    for definition in (*DATA_TOOLS, *KNOWLEDGE_TOOLS):
        assert registry.get(definition.name) is definition
    assert {name: registry.get(name).kind for name in registry.names()} == {
        "rag_search": "runtime",
        "sql_query": "runtime",
        "template_query": "runtime",
        "describe_table": "capability",
        "run_sql": "capability",
        "search_documents": "capability",
        "submit_result": "control",
        "report_insufficient": "control",
        "submit_answer": "control",
        "report_no_evidence": "control",
    }


def test_each_capability_names_the_runtime_tool_that_really_runs():
    registry = tool_catalog()

    assert registry.get("run_sql").backed_by == "sql_query"
    assert registry.get("search_documents").backed_by == "rag_search"
    # Reads the task's frozen schema snapshot only; nothing outside the task.
    assert registry.get("describe_table").backed_by is None


def test_specs_are_generated_from_the_definitions():
    assert DATA_TOOL_SPECS == [ToolSpec.from_definition(d) for d in DATA_TOOLS]
    assert KNOWLEDGE_TOOL_SPECS == [
        ToolSpec.from_definition(d) for d in KNOWLEDGE_TOOLS
    ]


RUN_SQL = next(d for d in DATA_TOOLS if d.name == "run_sql")
SUBMIT = next(d for d in DATA_TOOLS if d.name == "submit_result")


@pytest.mark.parametrize(
    ("broken", "why"),
    [
        (replace(RUN_SQL, model_text=None), "capability without model text"),
        (replace(SUBMIT, model_text=None), "control without model text"),
        (replace(RUN_SQL, backed_by="template_query_v9"), "backed by nothing"),
    ],
)
def test_model_facing_rules_refuse_startup(broken, why):
    assert validate_definitions((*catalog.TOOLS, broken)), why


def test_a_spec_needs_model_text():
    with pytest.raises(ValueError):
        ToolSpec.from_definition(catalog.TOOLS[0])


def test_model_text_renders_into_the_description_the_model_reads():
    text = ModelText(
        purpose="用途",
        when_to_use="何时",
        when_not_to_use="不用",
        example={"a": 1},
        common_errors=("错1", "错2"),
    )

    description = ToolSpec.from_definition(
        replace(RUN_SQL, model_text=text)
    ).to_openai()["function"]["description"]

    assert description == (
        '用途\n何时用：何时\n何时不用：不用\n示例参数：{"a": 1}\n常见错误：错1；错2'
    )
