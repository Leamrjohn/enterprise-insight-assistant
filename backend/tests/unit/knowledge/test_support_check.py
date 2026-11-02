"""Sentence-level support check: what the model decides and what code overrides."""

import json
from datetime import date

import pytest
from app.core.exceptions import StructuredOutputError
from app.core.gateway.base import ModelGateway
from app.modules.analysis.agent_protocol import AgentInput
from app.modules.analysis.tool_protocol import Tool, ToolInput, ToolOutput
from app.modules.knowledge.agent import KnowledgeAgent
from app.modules.knowledge.rag.support import check_support, split_sentences
from app.modules.knowledge.rag.validity import ValidityWindow

TODAY = date(2026, 11, 2)
WINDOW = ValidityWindow(TODAY, TODAY)
CURRENT = {"chunk_id": 1, "document_id": 1, "content": "上限520元", "score": 0.9}
RETIRED = {
    "chunk_id": 2,
    "document_id": 2,
    "content": "上限450元",
    "score": 0.9,
    "effective_from": "2023-01-01",
    "effective_to": "2024-12-31",
}


class _Gateway(ModelGateway):
    def __init__(self, *responses: str) -> None:
        self.responses = list(responses)
        self.prompts: list[str] = []

    def chat(self, prompt, system_prompt=None, *, json_mode=False):
        self.prompts.append(prompt)
        return self.responses.pop(0)

    def count_tokens(self, text):  # pragma: no cover - not used here
        return len(text)


def _verdicts(*items) -> str:
    return json.dumps(
        {
            "verdicts": [
                {"index": index, "verdict": verdict, "chunk_ids": chunks}
                for index, (verdict, chunks) in enumerate(items)
            ]
        }
    )


def _check(answer, response, evidences=None, facts=None):
    return check_support(
        _Gateway(response),
        question="上限是多少？",
        answer=answer,
        evidences=evidences or [CURRENT],
        window=WINDOW,
        confirmed_facts=facts,
    )


def test_split_keeps_decimals_and_drops_blanks():
    assert split_sentences("毛利率为12.5%。原因未知！\n") == [
        "毛利率为12.5%。",
        "原因未知！",
    ]


def test_supported_sentence_stays_with_its_citation():
    outcome = _check("上限520元。", _verdicts(("supported", [1])))
    assert outcome.answer == "上限520元。"
    assert outcome.cited_chunk_ids == [1]


def test_unsupported_sentence_is_removed_and_the_rest_stays():
    outcome = _check(
        "上限520元。因为成本上涨。",
        _verdicts(("supported", [1]), ("unsupported", [1])),
    )
    assert outcome.answer == "上限520元。"
    assert outcome.cited_chunk_ids == [1]


def test_not_applicable_sentence_is_removed():
    outcome = _check("上限520元。", _verdicts(("not_applicable", [1])))
    assert outcome.answer == "" and outcome.cited_chunk_ids == []


def test_sentence_without_a_verdict_is_removed():
    outcome = _check("上限520元。还有一句。", _verdicts(("supported", [1])))
    assert outcome.answer == "上限520元。"
    assert outcome.sentences[1].verdict == "missing"


def test_model_cannot_cite_a_chunk_that_was_not_retrieved():
    outcome = _check("上限520元。", _verdicts(("supported", [99])))
    assert outcome.answer == ""
    assert outcome.sentences[0].overruled == "no retrieved chunk cited"


def test_code_overrules_the_model_on_a_retired_document():
    outcome = _check("上限450元。", _verdicts(("supported", [2])), [CURRENT, RETIRED])
    assert outcome.answer == "" and outcome.cited_chunk_ids == []
    assert "not valid" in outcome.sentences[0].overruled


def test_retired_citation_is_dropped_when_a_valid_one_also_supports():
    outcome = _check("上限。", _verdicts(("supported", [2, 1])), [CURRENT, RETIRED])
    assert outcome.cited_chunk_ids == [1]


def test_retired_document_is_accepted_for_its_own_period():
    day = date(2024, 6, 1)
    outcome = check_support(
        _Gateway(_verdicts(("supported", [2]))),
        question="2024年6月的上限？",
        answer="上限450元。",
        evidences=[RETIRED],
        window=ValidityWindow(day, day),
    )
    assert outcome.cited_chunk_ids == [2]


def test_boundary_sentence_stays_but_supports_nothing():
    outcome = _check("资料未说明原因。", _verdicts(("boundary", [1])))
    assert outcome.answer == "资料未说明原因。"
    assert outcome.cited_chunk_ids == []


def test_data_fact_needs_real_confirmed_facts():
    without = _check("营收100元。", _verdicts(("data_fact", [])))
    assert without.answer == ""
    kept = _check("营收100元。", _verdicts(("data_fact", [])), facts=["营收100元"])
    assert kept.answer == "营收100元。"


@pytest.mark.parametrize(
    "response",
    ["not json", '{"verdicts": "x"}', '{"verdicts": [{"index": 0, "verdict": "ok"}]}'],
)
def test_malformed_check_output_raises(response):
    with pytest.raises(StructuredOutputError):
        _check("上限520元。", response)


class _ReadyTool(Tool):
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
                "evidences": [CURRENT],
                "system_prompt": "s",
                "user_prompt": "u",
                "allowed_chunk_ids": [1],
            },
        )


ANSWER = json.dumps(
    {"answer": "上限520元。因为成本上涨。", "citations": [{"chunk_id": 1}]},
    ensure_ascii=False,
)


def _run(*responses, support_check=True):
    gateway = _Gateway(*responses)
    output = KnowledgeAgent(
        rag_tool=_ReadyTool(), gateway=gateway, support_check=support_check
    ).run(AgentInput(question="上限是多少？", user_id=1, context={"company_id": 1}))
    return output, gateway


def test_agent_returns_only_the_checked_sentences():
    output, gateway = _run(ANSWER, _verdicts(("supported", [1]), ("unsupported", [])))
    assert output.answer == "上限520元。"
    assert [e["chunk_id"] for e in output.evidence] == [1]
    assert len(gateway.prompts) == 2


def test_agent_with_nothing_supported_cites_nothing():
    output, _ = _run(ANSWER, _verdicts(("unsupported", []), ("unsupported", [])))
    assert output.success and output.evidence == []
    assert output.error_code == "knowledge_no_supported_claim"
    assert "520" not in output.answer


def test_agent_fails_closed_when_the_check_output_is_malformed():
    output, _ = _run(ANSWER, "not json")
    assert output.evidence == []
    assert output.error_code == "knowledge_invalid_output"
    assert "520" not in output.answer


def test_agent_without_the_check_makes_one_call():
    output, gateway = _run(ANSWER, support_check=False)
    assert output.answer == "上限520元。因为成本上涨。"
    assert len(gateway.prompts) == 1
