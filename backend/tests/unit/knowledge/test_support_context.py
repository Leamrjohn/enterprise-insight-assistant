"""C5c: the support check records its context and, under enforce, refuses
what cannot fit."""

import json
from datetime import date

import pytest
from app.core.gateway.base import ModelGateway
from app.core.settings import get_settings
from app.modules.analysis.agent_protocol import AgentInput
from app.modules.analysis.tool_protocol import Tool, ToolInput, ToolOutput
from app.modules.knowledge.agent import KnowledgeAgent
from app.modules.knowledge.rag.support import check_support
from app.modules.knowledge.rag.validity import ValidityWindow
from app.modules.runtime import model_governance
from app.modules.runtime.context.engine import ContextBudgetExceeded

TODAY = date(2026, 11, 2)
CHUNK = {"chunk_id": 1, "document_id": 1, "content": "上限520元", "score": 0.9}
HUGE = {**CHUNK, "content": "差旅报销上限520元。" * 600}
VERDICTS = json.dumps(
    {"verdicts": [{"index": 0, "verdict": "supported", "chunk_ids": [1]}]}
)


class _Gateway(ModelGateway):
    def __init__(self, *responses: str) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    def chat(self, prompt, system_prompt=None, *, json_mode=False):
        self.calls.append(
            {
                "prompt": prompt,
                "system_prompt": system_prompt,
                "manifest": model_governance._context_manifest.get(),
            }
        )
        return self.responses.pop(0)

    def count_tokens(self, text):  # pragma: no cover - not used here
        return len(text)


def _mode(monkeypatch, mode: str) -> None:
    monkeypatch.setattr(get_settings(), "context_knowledge_mode", mode)


def _check(monkeypatch, mode: str, evidence=CHUNK) -> list[dict]:
    _mode(monkeypatch, mode)
    gateway = _Gateway(VERDICTS)
    check_support(
        gateway,
        question="上限是多少？",
        answer="上限520元。",
        evidences=[evidence],
        window=ValidityWindow(TODAY, TODAY),
        confirmed_facts=["八月销售额 100 元"],
    )
    return gateway.calls


@pytest.mark.parametrize("mode", ["shadow", "enforce"])
def test_the_check_sends_the_same_text_in_every_mode(mode, monkeypatch):
    off, other = _check(monkeypatch, "off")[0], _check(monkeypatch, mode)[0]
    assert (other["prompt"], other["system_prompt"]) == (
        off["prompt"],
        off["system_prompt"],
    )
    assert off["manifest"] is None


def test_shadow_and_enforce_name_their_manifests(monkeypatch):
    assert _check(monkeypatch, "shadow")[0]["manifest"].policy == "support/1:shadow"
    manifest = _check(monkeypatch, "enforce")[0]["manifest"]
    assert manifest.policy == "support/1"
    assert all(entry.action == "kept" for entry in manifest.sections)


def test_shadow_still_sends_a_check_that_would_not_fit(monkeypatch):
    calls = _check(monkeypatch, "shadow", evidence=HUGE)
    assert calls[0]["manifest"].over_budget is True
    assert HUGE["content"] in calls[0]["prompt"]


def test_enforce_refuses_an_oversized_check_before_any_model_call(monkeypatch):
    _mode(monkeypatch, "enforce")
    gateway = _Gateway(VERDICTS)
    with pytest.raises(ContextBudgetExceeded):
        check_support(
            gateway,
            question="上限是多少？",
            answer="上限520元。",
            evidences=[HUGE],
            window=ValidityWindow(TODAY, TODAY),
        )
    assert gateway.calls == []


class _ReadyTool(Tool):
    @property
    def name(self) -> str:
        return "rag_search"

    @property
    def description(self) -> str:
        return "returns one short chunk"

    def execute(self, input: ToolInput) -> ToolOutput:
        return ToolOutput(
            success=True,
            data={
                "status": "ready",
                "evidences": [CHUNK],
                "system_prompt": "s",
                "user_prompt": "u",
                "allowed_chunk_ids": [1],
            },
        )


def test_agent_cites_nothing_when_the_check_cannot_fit(monkeypatch):
    _mode(monkeypatch, "enforce")
    # The answer call is small and fits; checking its many sentences does not.
    answer = json.dumps(
        {"answer": "上限520元。" * 900, "citations": [{"chunk_id": 1}]},
        ensure_ascii=False,
    )
    gateway = _Gateway(answer, VERDICTS)
    output = KnowledgeAgent(
        rag_tool=_ReadyTool(), gateway=gateway, support_check=True
    ).run(AgentInput(question="上限是多少？", user_id=1, context={"company_id": 1}))
    # The answer was written, the check was refused: nothing unchecked is cited.
    assert len(gateway.calls) == 1
    assert output.success is True
    assert output.evidence == []
    assert output.error_code == "knowledge_support_context_budget_exceeded"
    assert "520" not in output.answer
