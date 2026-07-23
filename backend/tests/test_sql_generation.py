import pytest

from app.core.exceptions import StructuredOutputError
from app.core.gateway.base import ModelGateway
from app.services.sql_generation import (
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
