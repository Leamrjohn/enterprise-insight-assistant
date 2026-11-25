"""C5a: the reviews record their context and, under enforce, refuse what cannot fit."""

import json

import pytest
from app.core.settings import get_settings
from app.modules.analysis.agent_protocol import AgentInput
from app.modules.analysis.data.data_agent import DataAgent
from app.modules.analysis.data.sql_candidate import SQLCandidate
from app.modules.reporting.semantic_review_service import SemanticReviewService
from app.modules.runtime import model_governance
from app.modules.runtime.context.engine import (
    ContextBudgetExceeded,
    ContextPolicy,
    SectionRule,
    build_context,
)
from app.modules.workflow.orchestration import nodes as workflow_nodes

PLAN = {
    "action": "analyze",
    "route": "data_only",
    "reason": "查经营数据",
    "clarification_question": None,
    "response_message": None,
    "resolved_question": "华东区2025年8月销售额是多少？",
    "clarification": None,
    "intent": None,
    "evaluation_scope": None,
}
CANDIDATE = SQLCandidate(sql='SELECT 1 AS "销售额"', purpose="查销售额")
TOO_LONG = "华东区销售额" * 1500
EXECUTE = '{"decision":"execute","reason":"ok","missing_requirements":[]}'


class RecordingGateway:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls: list[dict] = []

    def chat(self, prompt, system_prompt=None, *, json_mode=False) -> str:
        self.calls.append(
            {
                "prompt": prompt,
                "system_prompt": system_prompt,
                "manifest": model_governance._context_manifest.get(),
            }
        )
        return self.responses[len(self.calls) - 1]


def _mode(monkeypatch, mode: str) -> None:
    monkeypatch.setattr(get_settings(), "context_review_mode", mode)


def _review_sql(monkeypatch, mode: str, responses=None, question="华东销售额"):
    _mode(monkeypatch, mode)
    gateway = RecordingGateway(responses or [EXECUTE])
    SemanticReviewService(gateway=gateway, sleeper=lambda _: None).review_sql(
        question=question, plan=PLAN, candidate=CANDIDATE, catalog=None
    )
    return gateway.calls


def _review_plan(monkeypatch, mode: str, question="华东区2025年8月销售额是多少？"):
    _mode(monkeypatch, mode)
    gateway = RecordingGateway(['{"action":"keep"}'])
    SemanticReviewService(gateway=gateway).review_plan(
        question=question, proposed_plan=PLAN, catalog=None
    )
    return gateway.calls


@pytest.mark.parametrize("mode", ["shadow", "enforce"])
def test_both_reviews_send_the_same_text_in_every_mode(mode, monkeypatch):
    for review in (_review_sql, _review_plan):
        off, other = review(monkeypatch, "off")[0], review(monkeypatch, mode)[0]
        assert (other["prompt"], other["system_prompt"]) == (
            off["prompt"],
            off["system_prompt"],
        )
        assert off["manifest"] is None


def test_shadow_and_enforce_name_their_manifests(monkeypatch):
    assert _review_plan(monkeypatch, "shadow")[0]["manifest"].policy == (
        "review_plan/1:shadow"
    )
    manifest = _review_sql(monkeypatch, "enforce")[0]["manifest"]
    assert manifest.policy == "review_sql/1"
    # Every payload key is a section of the policy, so enforce sends all of them.
    assert all(entry.action == "kept" for entry in manifest.sections)


def test_a_repair_records_the_same_manifest(monkeypatch):
    calls = _review_sql(monkeypatch, "enforce", responses=["not json", EXECUTE])
    assert len(calls) == 2
    assert calls[1]["manifest"] is calls[0]["manifest"]


def test_shadow_still_sends_a_review_that_would_not_fit(monkeypatch):
    calls = _review_sql(monkeypatch, "shadow", question=TOO_LONG)
    assert calls[0]["manifest"].over_budget is True
    assert TOO_LONG in json.loads(calls[0]["prompt"])["question"]


@pytest.mark.parametrize("review", ["sql", "plan", "evidence"])
def test_enforce_refuses_an_oversized_review_before_any_model_call(review, monkeypatch):
    _mode(monkeypatch, "enforce")
    gateway = RecordingGateway([EXECUTE])
    service = SemanticReviewService(gateway=gateway)
    with pytest.raises(ContextBudgetExceeded):
        if review == "sql":
            service.review_sql(
                question=TOO_LONG, plan=PLAN, candidate=CANDIDATE, catalog=None
            )
        elif review == "plan":
            service.review_plan(question=TOO_LONG, proposed_plan=PLAN, catalog=None)
        else:
            service.review_evidence(
                question=TOO_LONG,
                plan=PLAN,
                data_result={},
                knowledge_result={},
                report={},
            )
    assert gateway.calls == []
    assert service.model_attempts == 0


def test_shadow_evidence_review_is_sent_as_before(monkeypatch):
    _mode(monkeypatch, "shadow")
    gateway = RecordingGateway(
        ['{"verdict":"supported","reason":"ok","limitations":[]}']
    )
    SemanticReviewService(gateway=gateway).review_evidence(
        question=TOO_LONG, plan=PLAN, data_result={}, knowledge_result={}, report={}
    )
    assert len(gateway.calls) == 1
    assert gateway.calls[0]["manifest"].over_budget is True


def _exceeded() -> ContextBudgetExceeded:
    policy = ContextPolicy(
        node="t", version="t/1", budget_tokens=1, sections={"q": SectionRule()}
    )
    return ContextBudgetExceeded(build_context(policy, {"q": "问" * 10}))


class _RefusingReviewer:
    model_attempts = 0

    def __init__(self, *args, **kwargs) -> None:
        pass

    def review_sql(self, **kwargs):
        raise _exceeded()

    def review_plan(self, **kwargs):
        raise _exceeded()


class _Generator:
    def generate(self, question, **kwargs):
        return SQLCandidate(
            sql='SELECT SUM(o.total_amount) AS "销售额" FROM sales_orders AS o',
            purpose="查销售额",
            query_contract={
                "required_concepts": ["销售额"],
                "expected_columns": ["销售额"],
                "result_kind": "aggregate",
                "metric_definition_ref": "revenue/v1",
                "time_scope_column": "sales_orders.order_date",
            },
        )


class _UnusedTool:
    def execute(self, input):
        raise AssertionError("the query runs only after its review passed")


def test_data_agent_stops_when_the_sql_review_cannot_fit():
    agent = DataAgent(
        sql_generator=_Generator(),
        sql_tool=_UnusedTool(),
        semantic_reviewer=_RefusingReviewer(),
    )
    result = agent.run(
        AgentInput(
            question="八月销售额是多少？",
            user_id=1,
            context={
                "semantic_review_enabled": True,
                "plan": {"intent": {"required_capabilities": ["销售额"]}},
            },
        )
    )
    assert result.success is False
    assert result.error_code == "sql_review_context_budget_exceeded"


def test_plan_review_that_cannot_fit_asks_back_without_retrying(monkeypatch):
    monkeypatch.setattr(
        workflow_nodes.planner, "SemanticReviewService", _RefusingReviewer
    )
    result = workflow_nodes.planner_semantic_review_node(
        {
            "question": "华东区2025年8月销售额是多少？",
            "semantic_review_enabled": True,
            "plan": PLAN,
            "planner_result": {"attempts": {"model_attempts": 1}},
            "checkpoint_callback": lambda *_: None,
        }
    )
    # Same path as an unparseable review: ask back, and do not retry.
    assert result["semantic_review_outcome"]["status"] == "repairable_error"
    assert result["semantic_review_outcome"]["error_code"] == "semantic_review_failed"
    assert result["plan"]["action"] == "needs_clarification"
