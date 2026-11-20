"""C4c: SQL generation records its context and, under enforce, refuses what cannot fit."""

import pytest
from app.core.settings import get_settings
from app.modules.analysis.agent_protocol import AgentInput
from app.modules.analysis.data.data_agent import DataAgent
from app.modules.analysis.data.sql_generation import SQLGenerationService
from app.modules.runtime import model_governance
from app.modules.runtime.context.engine import ContextBudgetExceeded

CANDIDATE = (
    '{"sql":"SELECT o.total_amount FROM sales_orders AS o","purpose":"查询销售额"}'
)
QUESTION = "华东区2025年8月已交付订单销售额是多少？"
TOO_LONG = "华东区销售额" * 1500


class RecordingGateway:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def chat(self, prompt, system_prompt=None, *, json_mode=False) -> str:
        self.calls.append(
            {
                "prompt": prompt,
                "system_prompt": system_prompt,
                "manifest": model_governance._context_manifest.get(),
            }
        )
        return CANDIDATE


class UnusedSQLTool:
    def execute(self, input):
        raise AssertionError("no SQL may run when generation was refused")


def _generate(mode: str, monkeypatch, question: str = QUESTION, **kwargs) -> dict:
    monkeypatch.setattr(get_settings(), "context_sql_mode", mode)
    gateway = RecordingGateway()
    SQLGenerationService(gateway=gateway).generate(question, **kwargs)
    assert len(gateway.calls) == 1
    return gateway.calls[0]


def _sections(manifest) -> set[str]:
    return {entry.name for entry in manifest.sections}


@pytest.mark.parametrize("mode", ["shadow", "enforce"])
def test_the_prompt_is_the_same_in_every_mode(mode, monkeypatch):
    kwargs = {"required_concepts": ["销售额"]}
    off = _generate("off", monkeypatch, **kwargs)
    other = _generate(mode, monkeypatch, **kwargs)
    assert (other["prompt"], other["system_prompt"]) == (
        off["prompt"],
        off["system_prompt"],
    )
    assert off["manifest"] is None


def test_shadow_marks_its_manifest(monkeypatch):
    call = _generate("shadow", monkeypatch)
    assert call["manifest"].policy == "sql/1:shadow"
    assert _sections(call["manifest"]) == {"system", "question"}


def test_a_repair_records_the_previous_sql(monkeypatch):
    call = _generate(
        "enforce",
        monkeypatch,
        repair_reason="sql_validation_failed",
        previous_sql="SELECT 1",
        required_concepts=["销售额"],
    )
    assert call["manifest"].policy == "sql/1"
    assert _sections(call["manifest"]) == {
        "system",
        "question",
        "instructions",
        "previous_sql",
    }


def test_shadow_still_sends_what_would_not_fit(monkeypatch):
    call = _generate("shadow", monkeypatch, question=TOO_LONG)
    assert call["manifest"].over_budget is True


def test_enforce_refuses_before_calling_the_model(monkeypatch):
    monkeypatch.setattr(get_settings(), "context_sql_mode", "enforce")
    gateway = RecordingGateway()
    with pytest.raises(ContextBudgetExceeded) as raised:
        SQLGenerationService(gateway=gateway).generate(TOO_LONG)
    assert gateway.calls == []
    assert raised.value.action == "reject"


def test_data_agent_stops_without_retrying_or_counting_a_call(monkeypatch):
    monkeypatch.setattr(get_settings(), "context_sql_mode", "enforce")
    gateway = RecordingGateway()
    agent = DataAgent(
        sql_generator=SQLGenerationService(gateway=gateway), sql_tool=UnusedSQLTool()
    )
    result = agent.run(AgentInput(question=TOO_LONG, user_id=1))
    assert result.success is False
    assert result.error_code == "sql_context_budget_exceeded"
    assert result.attempts["model_attempts"] == 0
    assert gateway.calls == []
