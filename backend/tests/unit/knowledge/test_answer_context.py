"""C5b: the Knowledge answer records its context and, under enforce, refuses
what cannot fit."""

import json

import pytest
from app.core.gateway.base import ModelGateway
from app.core.settings import get_settings
from app.modules.analysis.agent_protocol import AgentInput
from app.modules.analysis.tool_protocol import Tool, ToolInput, ToolOutput
from app.modules.knowledge.agent import KnowledgeAgent
from app.modules.knowledge.schemas import RetrievalBrief
from app.modules.runtime import model_governance
from app.modules.runtime.context.manifest import content_hash

SENT = {"chunk_id": 1, "document_id": 1, "content": "上限520元", "score": 0.9}
# Retrieved, but past build_prompt's cap: never in front of the model.
NOT_SENT = {"chunk_id": 2, "document_id": 2, "content": "上限450元", "score": 0.5}
HUGE = {**SENT, "content": "差旅报销上限520元。" * 900}
FACT = {"fact_id": "f1", "statement": "八月差旅费 300 元"}
ANSWER = json.dumps(
    {"answer": "上限520元。", "citations": [{"chunk_id": 1}]}, ensure_ascii=False
)


class _Gateway(ModelGateway):
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def chat(self, prompt, system_prompt=None, *, json_mode=False):
        self.calls.append(
            {
                "prompt": prompt,
                "system_prompt": system_prompt,
                "manifest": model_governance._context_manifest.get(),
            }
        )
        return ANSWER

    def count_tokens(self, text):  # pragma: no cover - not used here
        return len(text)


class _Tool(Tool):
    def __init__(self, evidences: list[dict]) -> None:
        self.evidences = evidences

    @property
    def name(self) -> str:
        return "rag_search"

    @property
    def description(self) -> str:
        return "returns fixed evidence"

    def execute(self, input: ToolInput) -> ToolOutput:
        return ToolOutput(
            success=True,
            data={
                "status": "ready",
                "evidences": self.evidences,
                "system_prompt": "s",
                "user_prompt": "资料：" + self.evidences[0]["content"],
                "allowed_chunk_ids": [1],
            },
        )


def _run(monkeypatch, mode: str, evidences=(SENT, NOT_SENT), facts=(FACT,)):
    monkeypatch.setattr(get_settings(), "context_knowledge_mode", mode)
    gateway = _Gateway()
    output = KnowledgeAgent(rag_tool=_Tool(list(evidences)), gateway=gateway).run(
        AgentInput(
            question="上限是多少？",
            user_id=1,
            context={"company_id": 1, "confirmed_facts": list(facts)},
        )
    )
    return output, gateway.calls


def _section(manifest, name: str):
    return next(entry for entry in manifest.sections if entry.name == name)


@pytest.mark.parametrize("mode", ["shadow", "enforce"])
def test_the_answer_sends_the_same_text_in_every_mode(mode, monkeypatch):
    _, off = _run(monkeypatch, "off")
    _, other = _run(monkeypatch, mode)
    assert (other[0]["prompt"], other[0]["system_prompt"]) == (
        off[0]["prompt"],
        off[0]["system_prompt"],
    )
    assert off[0]["manifest"] is None


def test_shadow_and_enforce_name_their_manifests(monkeypatch):
    _, calls = _run(monkeypatch, "shadow")
    assert calls[0]["manifest"].policy == "knowledge_answer/2:shadow"
    _, calls = _run(monkeypatch, "enforce")
    assert calls[0]["manifest"].policy == "knowledge_answer/2"
    assert all(entry.action == "kept" for entry in calls[0]["manifest"].sections)


def test_the_manifest_measures_what_the_model_was_shown(monkeypatch):
    _, calls = _run(monkeypatch, "shadow")
    manifest = calls[0]["manifest"]
    # Only the chunks build_prompt selected, not everything retrieved.
    assert _section(manifest, "evidences").content_hash == content_hash(["上限520元"])
    # The question the prompt carries: the brief, facts included.
    asked = RetrievalBrief(
        question="上限是多少？", confirmed_fact_statements=[FACT["statement"]]
    ).render_query()
    assert _section(manifest, "question").content_hash == content_hash(asked)
    assert _section(manifest, "confirmed_facts").content_hash == content_hash(
        [FACT["statement"]]
    )


def test_without_facts_none_are_measured(monkeypatch):
    _, calls = _run(monkeypatch, "shadow", facts=())
    manifest = calls[0]["manifest"]
    assert _section(manifest, "confirmed_facts").content_hash == content_hash([])
    assert _section(manifest, "question").content_hash == content_hash("上限是多少？")


def test_shadow_still_sends_an_answer_that_would_not_fit(monkeypatch):
    _, calls = _run(monkeypatch, "shadow", evidences=(HUGE,))
    assert calls[0]["manifest"].over_budget is True


def test_enforce_refuses_an_oversized_answer_before_any_model_call(monkeypatch):
    output, calls = _run(monkeypatch, "enforce", evidences=(HUGE,))
    assert calls == []
    assert output.success is True
    assert output.evidence == []
    assert output.error_code == "knowledge_answer_context_budget_exceeded"
