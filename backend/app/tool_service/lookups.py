"""T11a: lookups the data model calls by name, each over the task's own source.

Every query here is built by code from declared table and column names, never
from the model's text, and still passes the same SQL validation and read-only
execution as sql_query.  A name the catalog does not know is handed back with
the choices, so the model can correct it.
"""

from collections.abc import Callable
from typing import Any

from app.modules.analysis.catalog.semantic_catalog import FILTER_VALUE_DEFINITIONS
from app.modules.analysis.catalog.snapshot_catalog import SnapshotCatalog
from app.modules.analysis.data.sql_tool import SQLTool
from app.modules.analysis.metrics.metric_catalog import (
    METRIC_DEFINITIONS,
    MetricDefinition,
)
from app.modules.analysis.tool_protocol import ToolInput, ToolOutput
from app.modules.organizations.models import BusinessDataSource

MAX_VALUES = 50

Handler = Callable[[dict[str, Any]], Any]
ReadOnlySQL = Callable[[str], ToolOutput]


def _has(catalog: SnapshotCatalog, column: str) -> bool:
    table, name = column.split(".", 1)
    return name in catalog.tables.get(table, frozenset())


def available_metrics(catalog: SnapshotCatalog) -> list[MetricDefinition]:
    """The metrics whose every column is in this company's snapshot."""
    return [
        definition
        for definition in METRIC_DEFINITIONS.values()
        if all(_has(catalog, column) for column in definition.source_columns)
    ]


def _chosen(
    metrics: list[MetricDefinition], name: str | None
) -> list[MetricDefinition]:
    if name is None:
        return metrics
    return [
        definition
        for definition in metrics
        if name
        in (
            definition.reference,
            definition.reference.split("/", 1)[0],
            definition.display_name,
        )
    ]


def _unknown(what: str, name: str, choices: list[str]) -> ToolOutput:
    return ToolOutput(
        success=False,
        error=f"没有这个{what}：{name}",
        error_code="tool_arguments_invalid",
        repairable=True,
        model_feedback=f"没有这个{what}：{name}。可选：{'、'.join(choices) or '无'}",
    )


def _describe(definition: MetricDefinition) -> dict[str, Any]:
    return {
        "reference": definition.reference,
        "name": definition.display_name,
        "unit": definition.unit,
        "aggregate": definition.aggregate_display,
        "time_column": definition.time_column,
        "mandatory_filters": [
            {"column": column, "equals": value}
            for column, value in definition.mandatory_equals
        ],
        "rounding_scale": definition.rounding_scale,
    }


def _readonly_sql(source: BusinessDataSource, catalog: SnapshotCatalog) -> ReadOnlySQL:
    tool = SQLTool(data_source=source, snapshot_catalog=catalog)
    return lambda sql: tool.execute(ToolInput(parameters={"sql": sql}))


def metric_lookup(source: BusinessDataSource, catalog: SnapshotCatalog) -> Handler:
    del source  # the definitions are code; the snapshot says which ones apply

    def run(arguments: dict[str, Any]) -> Any:
        metrics = available_metrics(catalog)
        chosen = _chosen(metrics, arguments.get("name"))
        if not chosen:
            names = [definition.display_name for definition in metrics]
            return _unknown("指标", arguments["name"], names)
        return {"metrics": [_describe(definition) for definition in chosen]}

    return run


def dimension_list(source: BusinessDataSource, catalog: SnapshotCatalog) -> Handler:
    run_sql = _readonly_sql(source, catalog)

    def run(arguments: dict[str, Any]) -> Any:
        field = arguments["field"]
        fields = [name for name in FILTER_VALUE_DEFINITIONS if _has(catalog, name)]
        if field not in fields:
            return _unknown("可列出取值的字段", field, fields)
        # field is one of the declared names above, so it is safe to place in SQL.
        table, column = field.split(".", 1)
        result = run_sql(
            f"SELECT DISTINCT {column} AS value FROM {table} "
            f"WHERE {column} IS NOT NULL ORDER BY value LIMIT {MAX_VALUES + 1}"
        )
        if not result.success:
            return result
        values = [row[0] for row in result.data["rows"]]
        meanings = FILTER_VALUE_DEFINITIONS[field]
        return {
            "field": field,
            "values": [
                {"value": value, "meaning": meanings.get(str(value))}
                for value in values[:MAX_VALUES]
            ],
            "truncated": len(values) > MAX_VALUES,
        }

    return run


def data_freshness(source: BusinessDataSource, catalog: SnapshotCatalog) -> Handler:
    run_sql = _readonly_sql(source, catalog)

    def run(arguments: dict[str, Any]) -> Any:
        metrics = available_metrics(catalog)
        chosen = _chosen(metrics, arguments.get("metric"))
        if not chosen:
            names = [definition.display_name for definition in metrics]
            return _unknown("指标", arguments["metric"], names)
        spans: dict[str, list[Any]] = {}  # metrics often share one time column
        coverage = []
        for definition in chosen:
            if definition.time_column not in spans:
                table, column = definition.time_column.split(".", 1)
                result = run_sql(
                    f"SELECT MIN({column}) AS earliest, MAX({column}) AS latest "
                    f"FROM {table}"
                )
                if not result.success:
                    return result
                spans[definition.time_column] = list(result.data["rows"][0])
            earliest, latest = spans[definition.time_column]
            coverage.append(
                {
                    "reference": definition.reference,
                    "name": definition.display_name,
                    "time_column": definition.time_column,
                    "earliest": earliest,
                    "latest": latest,
                }
            )
        return {"metrics": coverage}

    return run
