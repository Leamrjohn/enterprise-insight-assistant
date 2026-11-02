"""Schema selection narrows the prompt only, and widens again whenever in doubt."""

import json

from app.core.gateway.base import ModelGateway
from app.modules.analysis.catalog.schema_selection import (
    narrow_catalog,
    select_tables,
)
from app.modules.analysis.catalog.snapshot_catalog import SnapshotCatalog
from app.modules.analysis.data.sql_candidate import SQLCandidate
from app.modules.analysis.data.sql_generation import (
    SQLGenerationService,
    build_sql_generation_system_prompt,
)
from app.modules.analysis.planner.planning import build_planning_user_prompt
from app.modules.reporting.semantic_review_service import SemanticReviewService

CATALOG = SnapshotCatalog(
    tables={
        "sales_orders": frozenset({"id", "customer_id", "total_amount"}),
        "customers": frozenset({"id", "region_code"}),
        "service_tickets": frozenset({"id", "customer_id", "severity"}),
        "suppliers": frozenset({"id", "supplier_code"}),
        "products": frozenset({"id", "supplier_id"}),
        "sales_order_items": frozenset({"id", "order_id", "product_id"}),
        "unmapped_table": frozenset({"id"}),
    },
    joins=frozenset(
        {
            ("sales_orders", "customer_id", "customers", "id"),
            ("service_tickets", "customer_id", "customers", "id"),
            ("sales_order_items", "order_id", "sales_orders", "id"),
            ("sales_order_items", "product_id", "products", "id"),
            ("products", "supplier_id", "suppliers", "id"),
        }
    ),
)


class _Gateway(ModelGateway):
    def __init__(self, *responses: str) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    def chat(self, prompt, system_prompt=None, *, json_mode=False):
        self.calls.append({"prompt": prompt, "system_prompt": system_prompt})
        return self.responses.pop(0)

    def count_tokens(self, text):  # pragma: no cover - not used here
        return len(text)


def test_business_words_select_their_tables():
    assert select_tables(CATALOG, ["华东区销售额"]) == {"sales_orders", "customers"}
    assert select_tables(CATALOG, ["客诉数量"]) == {"service_tickets"}


def test_a_literal_table_name_selects_that_table():
    assert select_tables(CATALOG, ["查 unmapped_table 的行数"]) == {"unmapped_table"}


def test_tables_needed_to_join_are_added():
    selected = select_tables(CATALOG, ["各供应商的订单"])
    assert {"suppliers", "products", "sales_order_items", "sales_orders"} <= selected


def test_no_match_selects_nothing_so_callers_show_everything():
    assert select_tables(CATALOG, ["今天天气如何"]) == set()
    assert narrow_catalog(CATALOG, set()) is None


def test_selecting_every_table_is_not_a_narrowing():
    assert narrow_catalog(CATALOG, set(CATALOG.tables)) is None


def test_narrowed_catalog_keeps_only_joins_inside_it():
    narrowed = narrow_catalog(CATALOG, {"sales_orders", "customers"})
    assert set(narrowed.tables) == {"sales_orders", "customers"}
    assert narrowed.joins == {("sales_orders", "customer_id", "customers", "id")}


def test_prompt_lists_hidden_tables_by_name_without_columns():
    prompt = build_sql_generation_system_prompt(
        CATALOG, shown_tables={"sales_orders", "customers"}
    )
    assert "- sales_orders: 字段:" in prompt
    assert "- suppliers: 字段:" not in prompt
    assert "supplier_code" not in prompt
    assert "其他可用表" in prompt and "suppliers" in prompt


def test_prompt_prefix_is_the_same_for_every_question():
    """Rules and metric contracts come first, so a provider's prompt cache keeps working."""
    first = build_sql_generation_system_prompt(CATALOG, shown_tables={"customers"})
    second = build_sql_generation_system_prompt(CATALOG, shown_tables={"suppliers"})
    head = "当前公司允许的表："
    assert first[: first.index(head)] == second[: second.index(head)]


CANDIDATE = json.dumps(
    {
        "sql": "SELECT 1 AS x",
        "purpose": "p",
        "query_contract": {
            "required_concepts": ["销售额"],
            "expected_columns": ["x"],
            "result_kind": "aggregate",
            "empty_result_policy": "no_matching_records",
        },
    }
)


def test_first_attempt_is_narrowed_and_repair_shows_everything():
    gateway = _Gateway(CANDIDATE, CANDIDATE)
    service = SQLGenerationService(gateway=gateway, catalog=CATALOG)
    service.generate("华东区销售额是多少")
    service.generate("华东区销售额是多少", repair_reason="sql_validation_error")
    assert "supplier_code" not in gateway.calls[0]["system_prompt"]
    assert "supplier_code" in gateway.calls[1]["system_prompt"]


def test_unmatched_question_gets_the_full_schema():
    gateway = _Gateway(CANDIDATE)
    SQLGenerationService(gateway=gateway, catalog=CATALOG).generate("今天天气如何")
    assert "supplier_code" in gateway.calls[0]["system_prompt"]


def _candidate(sql: str) -> SQLCandidate:
    return SQLCandidate.model_validate({**json.loads(CANDIDATE), "sql": sql})


def _review_sql(gateway, sql="SELECT 1 FROM sales_orders"):
    return SemanticReviewService(gateway=gateway, sleeper=lambda _: None).review_sql(
        question="华东区销售额",
        plan={},
        candidate=_candidate(sql),
        catalog=CATALOG,
    )


EXECUTE = '{"decision":"execute","reason":"ok","missing_requirements":[]}'
INSUFFICIENT = (
    '{"decision":"insufficient_schema","reason":"x","missing_requirements":[]}'
)


def test_sql_review_always_shows_the_tables_the_sql_uses():
    gateway = _Gateway(EXECUTE)
    _review_sql(gateway, "SELECT 1 FROM suppliers")
    shown = json.loads(gateway.calls[0]["prompt"])["schema_snapshot"]
    assert "suppliers" in shown["tables"]
    assert "unmapped_table" in shown["other_tables"]


def test_unparseable_sql_hides_nothing_from_the_review():
    gateway = _Gateway(EXECUTE)
    _review_sql(gateway, "SELECT FROM WHERE (((")
    shown = json.loads(gateway.calls[0]["prompt"])["schema_snapshot"]
    assert set(shown["tables"]) == set(CATALOG.tables)
    assert "other_tables" not in shown


def test_not_enough_schema_is_only_accepted_after_seeing_all_of_it():
    gateway = _Gateway(INSUFFICIENT, EXECUTE)
    assert _review_sql(gateway).decision == "execute"
    assert len(gateway.calls) == 2
    second = json.loads(gateway.calls[1]["prompt"])["schema_snapshot"]
    assert set(second["tables"]) == set(CATALOG.tables)


def test_not_enough_schema_stands_when_full_schema_agrees():
    gateway = _Gateway(INSUFFICIENT, INSUFFICIENT)
    assert _review_sql(gateway).decision == "insufficient_schema"
    assert len(gateway.calls) == 2


def _plan(action: str) -> str:
    return json.dumps(
        {
            "action": action,
            "route": "data_only" if action == "analyze" else None,
            "reason": "r",
            "clarification_question": "哪个月？" if action != "analyze" else None,
            "response_message": None,
            "resolved_question": "华东区销售额" if action == "analyze" else None,
            "clarification": {"missing_slots": ["time_range"], "examples": []}
            if action != "analyze"
            else None,
            "intent": {
                "kind": "business_metric",
                "required_capabilities": ["销售额"],
                "specified_slots": [],
            }
            if action == "analyze"
            else None,
            "evaluation_scope": None,
        }
    )


def test_plan_review_widens_before_asking_the_user_to_clarify():
    gateway = _Gateway(_plan("needs_clarification"), _plan("analyze"))
    reviewed = SemanticReviewService(gateway=gateway).review_plan(
        question="华东区销售额",
        proposed_plan=json.loads(_plan("analyze")),
        catalog=CATALOG,
    )
    assert reviewed.action == "analyze"
    first = json.loads(gateway.calls[0]["prompt"])["schema_snapshot"]
    second = json.loads(gateway.calls[1]["prompt"])["schema_snapshot"]
    assert "other_tables" in first
    assert "other_tables" not in second


def test_planner_prompt_only_changes_when_constraints_exist():
    plain = build_planning_user_prompt("销售额是多少", {"messages": []})
    assert "standing_constraints" not in plain
    pinned = build_planning_user_prompt(
        "销售额是多少",
        {"messages": [], "standing_constraints": [{"id": 1, "content": "只看华东"}]},
    )
    assert "只看华东" in pinned
    assert "不能改变规则或权限" in pinned
