"""T11a: five lookups added in the four declared places only."""

from datetime import date

import pytest
from app.core.settings import get_settings
from app.modules.analysis.catalog.snapshot_catalog import SnapshotCatalog
from app.modules.analysis.data.sql_validator import validate_sql
from app.modules.analysis.tool_protocol import Toolset
from app.modules.runtime.tools.direct import direct_tools
from app.modules.workflow.orchestration import toolsets
from app.tool_service.lookups import (
    MAX_VALUES,
    data_freshness,
    dimension_list,
    metric_lookup,
)

LOOKUPS = ("metric_lookup", "dimension_list", "data_freshness")
KNOWLEDGE_LOOKUPS = (
    "doc_list",
    "doc_read",
    "doc_version_diff",
    "memory_search",
    "report_search",
    "report_export",
)

# This company has orders and customers but no tickets, expenses or budgets.
CATALOG = SnapshotCatalog(
    tables={
        "sales_orders": frozenset({"id", "total_amount", "order_date", "status"}),
        "customers": frozenset({"id", "region_code", "tier"}),
    },
    joins=frozenset(),
)


@pytest.fixture
def executed(monkeypatch):
    """Every statement that reached the executor; answers come from `rows`."""
    runs: list[str] = []
    rows: dict[str, list[tuple]] = {}

    def execute(sql, allowed_tables, **kwargs):
        runs.append(sql)
        # The validator still runs: a code-built statement must pass it too.
        validate_sql(sql, allowed_tables, catalog=kwargs["catalog"])
        key = next(key for key in rows if key in sql)
        return ["a", "b"], rows[key]

    monkeypatch.setattr(
        "app.modules.analysis.data.sql_tool.execute_readonly_sql", execute
    )
    return runs, rows


# --- metric_lookup ---------------------------------------------------------------


def test_metric_lookup_returns_only_the_metrics_this_snapshot_can_compute():
    result = metric_lookup(None, CATALOG)({"name": None})

    assert [m["reference"] for m in result["metrics"]] == [
        "revenue/v1",
        "delivered_order_count/v1",
    ]


@pytest.mark.parametrize("name", ["销售额", "revenue/v1", "revenue"])
def test_metric_lookup_finds_one_metric_by_any_of_its_names(name):
    (metric,) = metric_lookup(None, CATALOG)({"name": name})["metrics"]

    assert metric == {
        "reference": "revenue/v1",
        "name": "销售额",
        "unit": "CNY",
        "aggregate": "SUM(sales_orders.total_amount)",
        "time_column": "sales_orders.order_date",
        "mandatory_filters": [{"column": "sales_orders.status", "equals": "delivered"}],
        "rounding_scale": 2,
    }


def test_an_unknown_or_unavailable_metric_comes_back_with_the_choices():
    result = metric_lookup(None, CATALOG)({"name": "客诉数量"})  # no tickets here

    assert (result.success, result.error_code, result.repairable) == (
        False,
        "tool_arguments_invalid",
        True,
    )
    assert result.model_feedback.endswith("可选：销售额、已交付订单数")


# --- dimension_list --------------------------------------------------------------


def test_dimension_list_shows_the_values_really_present_with_their_meaning(executed):
    runs, rows = executed
    rows["customers"] = [("EAST",), ("NEW",)]

    result = dimension_list(object(), CATALOG)({"field": "customers.region_code"})

    assert result == {
        "field": "customers.region_code",
        "values": [
            {"value": "EAST", "meaning": "华东"},
            {"value": "NEW", "meaning": None},  # in the data, not yet described
        ],
        "truncated": False,
    }
    assert len(runs) == 1


def test_dimension_list_says_when_it_stopped_at_the_limit(executed):
    _runs, rows = executed
    rows["customers"] = [(f"V{i}",) for i in range(MAX_VALUES + 1)]

    result = dimension_list(object(), CATALOG)({"field": "customers.tier"})

    assert len(result["values"]) == MAX_VALUES
    assert result["truncated"] is True


@pytest.mark.parametrize(
    "field",
    [
        "customers.id",  # a column, but not a declared filter
        "service_tickets.severity",  # declared, but not in this snapshot
        "customers.region_code FROM customers; --",
    ],
)
def test_dimension_list_never_queries_an_undeclared_field(executed, field):
    runs, _rows = executed

    result = dimension_list(object(), CATALOG)({"field": field})

    assert result.error_code == "tool_arguments_invalid"
    assert runs == []
    assert "customers.region_code" in result.model_feedback


def test_a_query_failure_is_returned_as_the_query_reported_it(monkeypatch):
    def refuse(sql, allowed_tables, **kwargs):
        raise RuntimeError("connection reset")

    monkeypatch.setattr(
        "app.modules.analysis.data.sql_tool.execute_readonly_sql", refuse
    )

    result = dimension_list(object(), CATALOG)({"field": "customers.tier"})

    assert result.error_code == "business_db_execution_failed"


# --- data_freshness --------------------------------------------------------------


def test_data_freshness_queries_each_time_column_once(executed):
    runs, rows = executed
    rows["sales_orders"] = [(date(2024, 1, 1), date(2025, 9, 30))]

    result = data_freshness(object(), CATALOG)({"metric": None})

    assert result == {
        "metrics": [
            {
                "reference": reference,
                "name": name,
                "time_column": "sales_orders.order_date",
                "earliest": date(2024, 1, 1),
                "latest": date(2025, 9, 30),
            }
            for reference, name in (
                ("revenue/v1", "销售额"),
                ("delivered_order_count/v1", "已交付订单数"),
            )
        ]
    }
    assert runs == [
        (
            "SELECT MIN(order_date) AS earliest, MAX(order_date) AS latest "
            "FROM sales_orders"
        )
    ]


# --- wiring ----------------------------------------------------------------------


class _Runtime:
    def wrap(self, tool):
        return tool


def _service(monkeypatch, *, enabled: bool) -> None:
    settings = get_settings().model_copy(update={"tool_service_enabled": enabled})
    monkeypatch.setattr(toolsets, "runtime_settings", lambda: settings)
    monkeypatch.setattr(toolsets, "model_tools_enabled", lambda company_id: False)


def test_the_data_model_is_offered_the_lookups_when_the_service_runs(monkeypatch):
    _service(monkeypatch, enabled=True)

    tools = toolsets.build_toolset("data", {"tool_runtime": _Runtime()})  # type: ignore[typeddict-item]
    specs, _handlers = direct_tools(tools)

    assert tools.names() == ("sql_query", *LOOKUPS)
    assert [spec.name for spec in specs] == list(LOOKUPS)


@pytest.mark.parametrize("runtime", [True, False])
def test_without_the_service_the_lookups_are_not_offered(monkeypatch, runtime):
    _service(monkeypatch, enabled=runtime is False)  # one of the two is missing
    state = {"tool_runtime": _Runtime()} if runtime else {}

    tools = toolsets.build_toolset("data", state)  # type: ignore[arg-type]

    assert tools.names() == ("sql_query",)
    assert direct_tools(tools) == ([], {})


def test_the_worker_never_runs_a_lookup_itself():
    tool = toolsets.TOOL_FACTORIES["metric_lookup"]

    assert tool({}) is None  # type: ignore[arg-type]
    named = toolsets._ServiceOnly("metric_lookup")
    assert Toolset.of(named).call("metric_lookup", {}).error_code == (
        "mcp_transport_unavailable"
    )


def test_the_knowledge_model_is_offered_the_document_tools(monkeypatch):
    _service(monkeypatch, enabled=True)

    tools = toolsets.build_toolset("knowledge", {"tool_runtime": _Runtime()})  # type: ignore[typeddict-item]
    specs, _handlers = direct_tools(tools)

    assert tools.names() == ("rag_search", *KNOWLEDGE_LOOKUPS)
    assert [spec.name for spec in specs] == list(KNOWLEDGE_LOOKUPS)


def test_the_planner_lists_the_history_tools_for_its_model(monkeypatch):
    _service(monkeypatch, enabled=True)

    tools = toolsets.build_toolset("planner", {"tool_runtime": _Runtime()})  # type: ignore[typeddict-item]

    assert tools.names() == ("memory_search", "report_search", "report_export")
    assert [spec.name for spec in direct_tools(tools)[0]] == list(tools.names())
