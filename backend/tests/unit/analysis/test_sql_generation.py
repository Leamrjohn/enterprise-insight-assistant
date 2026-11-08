import pytest
from app.core.exceptions import StructuredOutputError
from app.core.gateway.base import ModelGateway
from app.modules.analysis.catalog.snapshot_catalog import SnapshotCatalog
from app.modules.analysis.data.sql_generation import (
    SQLGenerationService,
    build_sql_generation_system_prompt,
)


class FakeGateway(ModelGateway):
    def __init__(self, response: str) -> None:
        self.response = response
        self.prompt: str | None = None
        self.system_prompt: str | None = None
        self.json_mode: bool | None = None

    def chat(
        self,
        prompt: str,
        system_prompt: str | None = None,
        *,
        json_mode: bool = False,
    ) -> str:
        self.prompt = prompt
        self.system_prompt = system_prompt
        self.json_mode = json_mode
        return self.response

    def count_tokens(self, text: str) -> int:
        return len(text)


def test_builds_prompt_from_controlled_business_catalogue() -> None:
    prompt = build_sql_generation_system_prompt()

    assert "sales_orders" in prompt
    assert "sales_orders.customer_id = customers.id" in prompt
    assert "销售额" in prompt
    assert "customers.region_code: EAST = 华东" in prompt
    assert "sales_orders.status: delivered = 已交付订单" in prompt
    assert "revenue/v1" in prompt
    assert "SUM(sales_orders.total_amount)" in prompt
    assert "固定筛选 sales_orders.status = delivered" in prompt
    assert "numeric_assertion" in prompt
    assert "business_documents" not in prompt
    assert "evaluation.scenario_truth" not in prompt


def test_generates_candidate_with_json_mode() -> None:
    gateway = FakeGateway(
        '{"sql":"SELECT o.total_amount FROM sales_orders AS o",'
        '"purpose":"查询已交付订单销售额"}'
    )
    service = SQLGenerationService(gateway=gateway)

    candidate = service.generate("已交付订单销售额是多少？")

    assert candidate.sql == "SELECT o.total_amount FROM sales_orders AS o"
    assert candidate.purpose == "查询已交付订单销售额"
    assert gateway.json_mode is True
    assert gateway.prompt is not None
    assert "已交付订单销售额是多少？" in gateway.prompt
    assert gateway.system_prompt is not None
    assert "允许的表" in gateway.system_prompt


def test_includes_frozen_required_concepts_in_generation_prompt() -> None:
    gateway = FakeGateway('{"sql":"SELECT 1 AS \\"销售额\\"","purpose":"查询销售额"}')
    service = SQLGenerationService(gateway=gateway)

    service.generate("查询销售额", required_concepts=["销售额指标", "华东区维度"])

    assert gateway.prompt is not None
    assert '"销售额指标"' in gateway.prompt
    assert '"华东区维度"' in gateway.prompt
    assert "逐字包含" in gateway.prompt


def test_includes_frozen_planner_scope_in_generation_prompt() -> None:
    gateway = FakeGateway('{"sql":"SELECT 1 AS \\"销售额\\"","purpose":"查询销售额"}')
    service = SQLGenerationService(gateway=gateway)

    service.generate(
        "查询华东区销售额",
        evaluation_scope={"entities": ["华东"], "period": "2025-08"},
    )

    assert gateway.prompt is not None
    assert '"华东"' in gateway.prompt
    assert '"2025-08"' in gateway.prompt
    assert "优先使用 scope 中的精确业务对象" in gateway.prompt
    assert "必须使用映射后的数据库值" in gateway.prompt


def test_maps_invalid_model_json_to_structured_output_error() -> None:
    service = SQLGenerationService(gateway=FakeGateway("not valid json"))

    with pytest.raises(StructuredOutputError, match="不符合约定 JSON 结构"):
        service.generate("查询销售额")


def test_builds_safe_repair_prompt_for_sql_semantic_error() -> None:
    previous_sql = "SELECT c.region_code, SUM(o.total_amount) FROM sales_orders AS o"
    gateway = FakeGateway(
        '{"sql":"SELECT o.total_amount FROM sales_orders AS o","purpose":"查询销售额"}'
    )
    service = SQLGenerationService(gateway=gateway)

    service.generate(
        "华东区销售额是多少？",
        repair_reason="sql_semantic_error",
        previous_sql=previous_sql,
    )

    assert gateway.prompt is not None
    assert previous_sql in gateway.prompt
    assert "上一次 SQL 的聚合、字段或关联语义不正确。" in gateway.prompt
    assert "sql_semantic_error" not in gateway.prompt


def test_builds_safe_repair_prompt_for_insufficient_metric_contract() -> None:
    gateway = FakeGateway('{"sql":"SELECT 1 AS \\"销售额\\"","purpose":"查询销售额"}')
    service = SQLGenerationService(gateway=gateway)

    service.generate(
        "华东区销售额是多少？",
        repair_reason="metric_contract_insufficient",
        previous_sql='SELECT 1 AS "销售额"',
    )

    assert gateway.prompt is not None
    assert "没有满足登记指标的聚合、固定筛选或血缘列要求" in gateway.prompt


def test_builds_prompt_from_company_snapshot_without_static_tables() -> None:
    catalog = SnapshotCatalog.from_snapshot(
        {
            "tables": {"inventory": [{"name": "on_hand"}, {"name": "sku"}]},
            "joins": [],
        }
    )

    prompt = build_sql_generation_system_prompt(catalog)

    assert "inventory" in prompt
    assert "on_hand" in prompt
    assert "sales_orders" not in prompt
    assert "无；禁止 JOIN" in prompt
    assert "当前契约快照约束可用的表、字段和 Join" in prompt
    assert "不得猜测枚举值" in prompt
    assert "每个会展示给用户的 SELECT 表达式都必须用中文业务别名" in prompt
    assert "purpose 也必须是面向业务用户的简短中文说明" in prompt


def test_builds_snapshot_prompt_with_registered_values_for_present_columns() -> None:
    catalog = SnapshotCatalog.from_snapshot(
        {
            "tables": {
                "customers": [{"name": "id"}, {"name": "region_code"}],
                "sales_orders": [
                    {"name": "customer_id"},
                    {"name": "status"},
                    {"name": "order_date"},
                    {"name": "total_amount"},
                ],
            },
            "joins": [
                {
                    "left_table": "sales_orders",
                    "left_column": "customer_id",
                    "right_table": "customers",
                    "right_column": "id",
                }
            ],
        }
    )

    prompt = build_sql_generation_system_prompt(catalog)

    assert "customers.region_code: EAST = 华东" in prompt
    assert "sales_orders.status: delivered = 已交付订单" in prompt
