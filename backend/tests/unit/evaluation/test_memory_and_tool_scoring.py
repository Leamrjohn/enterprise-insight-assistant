"""Scoring rules for the memory and tool baselines, and their fixture integrity."""

import json
from pathlib import Path

import pytest
from app.modules.evaluation.memory_selection import (
    score_memory_case,
    summarize_memory_cases,
)
from app.modules.evaluation.tool_selection import (
    score_tool_case,
    summarize_tool_cases,
    tools_for_decision,
)
from scripts.evaluation.run_tool_selection_evaluation import load_cases

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


def test_memory_case_passes_only_with_required_and_without_forbidden():
    assert score_memory_case(selected={"a"}, must_select=["a"], must_not_select=["b"])[
        "passed"
    ]
    missed = score_memory_case(selected=set(), must_select=["a"], must_not_select=[])
    assert missed["missed"] == ["a"] and not missed["passed"]
    violated = score_memory_case(
        selected={"a", "b"}, must_select=["a"], must_not_select=["b"]
    )
    assert violated["violations"] == ["b"] and not violated["passed"]


def test_memory_summary_counts_recall_and_isolation():
    rows = [
        {
            "case_id": "x",
            "found": ["a"],
            "missed": ["b"],
            "violations": ["c"],
            "isolation_violations": ["c"],
            "selected_count": 4,
            "passed": False,
        }
    ]
    summary = summarize_memory_cases(rows)
    assert summary["required_recall"] == 0.5
    assert summary["violations"] == 1
    assert summary["isolation_violations"] == 1
    assert summary["failed"] == ["x"]


def test_memory_fixture_references_known_keys():
    fixture = json.loads(
        (FIXTURES / "evaluation_memory" / "memory_scenarios_v1.json").read_text(
            encoding="utf-8"
        )
    )
    keys = {memory["key"] for memory in fixture["memories"]}
    for case in fixture["cases"]:
        assert set(case["must_select"]) <= keys, case["case_id"]
        assert set(case["must_not_select"]) <= keys, case["case_id"]


@pytest.mark.parametrize(
    ("called", "verdict"),
    [
        ({"sql_query"}, "correct"),
        (set(), "too_few_tools"),
        ({"sql_query", "rag_search"}, "too_many_tools"),
        ({"rag_search"}, "wrong_tools"),
    ],
)
def test_tool_case_verdicts(called, verdict):
    result = score_tool_case(
        called=frozenset(called), acceptable=[frozenset({"sql_query"})]
    )
    assert result["verdict"] == verdict


def test_forbidden_tool_is_counted_separately():
    result = score_tool_case(
        called=frozenset({"sql_query"}),
        acceptable=[frozenset()],
        forbidden=frozenset({"sql_query"}),
    )
    assert result["forbidden_called"] == ["sql_query"]
    assert result["verdict"] == "too_many_tools"


def test_unknown_decision_is_an_error_not_a_pass():
    assert tools_for_decision("analyze/made_up") is None
    result = score_tool_case(called=None, acceptable=[frozenset()])
    assert result["verdict"] == "error"


def test_tool_summary_reports_by_split():
    summary = summarize_tool_cases(
        [
            {
                "case_id": "a",
                "split": "development",
                "verdict": "correct",
                "forbidden_called": [],
            },
            {
                "case_id": "b",
                "split": "heldout",
                "verdict": "wrong_tools",
                "forbidden_called": ["sql_query"],
            },
        ]
    )
    assert summary["accuracy"] == 0.5
    assert summary["forbidden_calls"] == 1
    assert summary["not_correct"] == ["b"]


def test_tool_cases_combine_route_labels_and_extra_questions():
    cases = load_cases()
    ids = [case["case_id"] for case in cases]
    assert len(ids) == len(set(ids))
    assert len(cases) == 34 + 14
    for case in cases:
        assert case["acceptable"], case["case_id"]


# --- T11b: a node's first tool round -------------------------------------------


def test_lookup_cases_name_only_tools_their_node_offers():
    from scripts.evaluation.run_tool_selection_evaluation import (
        load_lookup_cases,
        node_tools,
    )

    offered = {
        node: {tool["function"]["name"] for tool in node_tools(node)}
        for node in ("data", "knowledge")
    }
    cases = load_lookup_cases()

    assert len(cases) == 21
    assert len({case["case_id"] for case in cases}) == 21
    for case in cases:
        for option in case["acceptable"]:
            assert option <= offered[case["node"]], case["case_id"]
    assert {"metric_lookup", "dimension_list", "data_freshness"} <= offered["data"]
    assert {"doc_version_diff", "memory_search", "report_export"} <= offered[
        "knowledge"
    ]


def test_node_lookup_scores_the_first_round_per_node():
    from app.core.gateway.base import ModelGateway, ToolCall, ToolChatResponse
    from scripts.evaluation.run_tool_selection_evaluation import (
        evaluate_node_lookups,
    )

    class Scripted(ModelGateway):
        def __init__(self, names):
            self.names = list(names)
            self.systems = []

        def chat(self, prompt, system_prompt=None, *, json_mode=False):
            raise AssertionError

        def chat_with_tools(self, messages, tools, *, tool_choice="auto"):
            self.systems.append(messages[0]["content"])
            name = self.names.pop(0)
            return ToolChatResponse(None, (ToolCall("c1", name, "{}"),))

        def count_tokens(self, text):
            return len(text)

    cases = [
        {
            "case_id": "a",
            "node": "data",
            "question": "数据到哪天",
            "acceptable": [frozenset({"data_freshness"})],
            "forbidden": frozenset(),
        },
        {
            "case_id": "b",
            "node": "knowledge",
            "question": "以前的结论",
            "acceptable": [frozenset({"memory_search"})],
            "forbidden": frozenset(),
        },
    ]
    gateway = Scripted(["data_freshness", "search_documents"])

    rows = evaluate_node_lookups(gateway, cases)

    assert [row["verdict"] for row in rows] == ["correct", "wrong_tools"]
    assert summarize_tool_cases(rows)["by_split"] == {"data": 1.0, "knowledge": 0.0}
    assert gateway.systems[0] != gateway.systems[1]  # each node's own prompt
