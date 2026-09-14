from app.modules.analysis.tool_protocol import ToolInput
from app.modules.analysis.template_query import TemplateQueryTool


def valid_parameters() -> dict:
    return {
        "query_id": "regional_revenue_comparison",
        "region": "EAST",
        "current_month": "2025-08-01",
        "comparison_month": "2025-07-01",
        "limit": 20,
    }


def test_template_query_tool_executes_registered_parameterized_query(monkeypatch):
    captured = {}

    def fake_execute(sql: str, parameters: dict):
        captured["sql"] = sql
        captured["parameters"] = parameters
        return ["region_code", "revenue_change"], [("EAST", -166405.92)]

    monkeypatch.setattr(
        "app.modules.analysis.template_query.execute_registered_readonly_query",
        fake_execute,
    )

    result = TemplateQueryTool().execute(ToolInput(parameters=valid_parameters()))

    assert result.success is True
    assert "SELECT" in captured["sql"]
    assert captured["parameters"]["region"] == "EAST"
    assert result.data == {
        "query_id": "regional_revenue_comparison",
        "parameters": valid_parameters(),
        "columns": ["region_code", "revenue_change"],
        "rows": [("EAST", -166405.92)],
    }


def test_template_query_tool_rejects_invalid_parameters_without_execution(monkeypatch):
    monkeypatch.setattr(
        "app.modules.analysis.template_query.execute_registered_readonly_query",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("executor must not run")
        ),
    )

    result = TemplateQueryTool().execute(
        ToolInput(parameters={"query_id": "run_any_sql"})
    )

    assert result.success is False
    assert result.error_code == "template_query_invalid_request"


def test_template_query_tool_hides_database_exception(monkeypatch):
    def raise_database_error(*_args, **_kwargs):
        raise RuntimeError("database details must not reach users")

    monkeypatch.setattr(
        "app.modules.analysis.template_query.execute_registered_readonly_query",
        raise_database_error,
    )

    result = TemplateQueryTool().execute(ToolInput(parameters=valid_parameters()))

    assert result.success is False
    assert result.error == "经营数据查询暂时无法完成。"
    assert result.error_code == "template_query_execution_failed"
