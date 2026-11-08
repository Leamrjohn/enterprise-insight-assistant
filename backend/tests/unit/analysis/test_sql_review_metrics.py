"""The SQL reviewer must see the same reviewed metric definitions as the generator."""

import json

from app.modules.analysis.catalog.snapshot_catalog import SnapshotCatalog
from app.modules.analysis.data.sql_candidate import SQLCandidate
from app.modules.reporting.semantic_review_service import SemanticReviewService


class _CapturingGateway:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def chat(self, prompt, system_prompt=None, *, json_mode=False):
        self.prompts.append((system_prompt or "") + prompt)
        return json.dumps(
            {"decision": "execute", "reason": "ok", "missing_requirements": []}
        )


def _review_prompt(tables: dict) -> str:
    gateway = _CapturingGateway()
    catalog = SnapshotCatalog.from_snapshot(
        {
            "tables": {
                table: [{"name": column} for column in columns]
                for table, columns in tables.items()
            },
            "joins": [],
        }
    )
    SemanticReviewService(gateway=gateway).review_sql(
        question="2025年8月客诉数量是多少？",
        plan={},
        candidate=SQLCandidate(
            sql="SELECT COUNT(t.id) FROM service_tickets t", purpose="统计客诉"
        ),
        catalog=catalog,
    )
    return gateway.prompts[0]


def test_reviewer_receives_the_definition_of_a_metric_in_the_snapshot():
    prompt = _review_prompt({"service_tickets": ["id", "opened_date"]})

    assert "ticket_count/v1" in prompt
    assert "COUNT(service_tickets.id)" in prompt
    assert "registered_metrics" in prompt


def test_reviewer_does_not_receive_metrics_the_snapshot_cannot_support():
    prompt = _review_prompt({"service_tickets": ["id", "opened_date"]})

    assert "revenue/v1" not in prompt
    assert "gross_profit/v1" not in prompt
