"""The model may search again, but scope, window and citations stay with code."""

import json

from app.core.gateway.base import ModelGateway, ToolCall, ToolChatResponse
from app.modules.analysis.agent_protocol import AgentInput
from app.modules.analysis.tool_protocol import Tool, ToolOutput
from app.modules.knowledge.tool_agent import ToolCallingKnowledgeAgent
from app.modules.runtime.tool_loop import LoopLimits


def _evidence(chunk_id=7, content="退货需要主管审批。"):
    return {
        "chunk_id": chunk_id,
        "document_id": 1,
        "content": content,
        "score": 0.9,
        "document_name": "制度",
    }


def _ready(*evidences):
    return ToolOutput(
        success=True,
        data={
            "status": "ready",
            "evidences": list(evidences) or [_evidence()],
            "system_prompt": "s",
            "user_prompt": "u",
            "allowed_chunk_ids": [e["chunk_id"] for e in evidences] or [7],
        },
    )


NOTHING = ToolOutput(
    success=True,
    data={"status": "insufficient_evidence", "answer": "无", "evidences": []},
)


def _call(name, arguments, call_id="c1"):
    return ToolChatResponse(
        None, (ToolCall(call_id, name, json.dumps(arguments, ensure_ascii=False)),)
    )


def _submit(chunk_id=7, answer="退货需要主管审批。"):
    return _call(
        "submit_answer", {"answer": answer, "citations": [{"chunk_id": chunk_id}]}
    )


class _Rag(Tool):
    def __init__(self, *outputs):
        self.outputs = list(outputs)
        self.seen = []

    @property
    def name(self):
        return "rag_search"

    @property
    def description(self):
        return "d"

    def execute(self, input):
        self.seen.append(input.parameters)
        return self.outputs.pop(0) if len(self.outputs) > 1 else self.outputs[0]


class _Scripted(ModelGateway):
    def __init__(self, responses, chat_output=None):
        self.responses = list(responses)
        self.chat_output = chat_output
        self.requests = []

    def chat(self, prompt, system_prompt=None, *, json_mode=False):
        return self.chat_output

    def chat_with_tools(self, messages, tools, *, tool_choice="auto"):
        self.requests.append(list(messages))
        return self.responses.pop(0)

    def count_tokens(self, text):
        return len(text)


def _agent(rag, gateway):
    return ToolCallingKnowledgeAgent(
        rag_tool=rag, gateway=gateway, limits=LoopLimits(backoff_seconds=0)
    )


def _input(question="退货流程是什么？", **context):
    return AgentInput(
        question=question,
        user_id=1,
        context={"company_id": 3, "document_ids": [1, 2], **context},
    )


def test_a_good_first_search_answers_in_one_model_round():
    gateway = _Scripted([_submit()])
    output = _agent(_Rag(_ready(_evidence())), gateway).run(_input())
    assert output.success
    assert output.answer == "退货需要主管审批。"
    assert output.evidence[0]["chunk_id"] == 7
    assert len(gateway.requests) == 1


def test_every_search_keeps_the_scope_and_window_set_by_code():
    rag = _Rag(NOTHING, _ready(_evidence()))
    gateway = _Scripted([_call("search_documents", {"query": "退货 审批"}), _submit()])
    _agent(rag, gateway).run(_input("2024年的退货流程是什么？"))
    assert rag.seen[1]["question"] == "退货 审批"
    for parameters in rag.seen:
        assert parameters["company_id"] == 3
        assert parameters["document_ids"] == [1, 2]
        assert parameters["validity_window"] == ["2024-01-01", "2024-12-31"]


def test_the_model_cannot_pass_scope_through_search_arguments():
    rag = _Rag(NOTHING)
    gateway = _Scripted(
        [
            _call("search_documents", {"query": "x", "company_id": 9}),
            _call("report_no_evidence", {"reason": "无"}),
        ]
    )
    output = _agent(rag, gateway).run(_input())
    assert len(rag.seen) == 1
    assert output.error_code == "insufficient_evidence"


def test_a_citation_that_was_never_retrieved_goes_back_to_the_model():
    gateway = _Scripted([_submit(chunk_id=999), _submit()])
    output = _agent(_Rag(_ready(_evidence())), gateway).run(_input())
    assert output.evidence[0]["chunk_id"] == 7
    tool_reply = json.loads(gateway.requests[-1][-1]["content"])
    assert tool_reply["unknown"] == [999]


def test_nothing_found_ends_as_the_fixed_routes_insufficient_evidence():
    gateway = _Scripted([_call("report_no_evidence", {"reason": "文档没有提到"})])
    output = _agent(_Rag(NOTHING), gateway).run(_input())
    assert output.success
    assert output.evidence == []
    assert output.error_code == "insufficient_evidence"


def test_searches_are_capped_and_repeats_refused():
    rag = _Rag(NOTHING)
    gateway = _Scripted(
        [
            _call("search_documents", {"query": "甲"}),
            _call("search_documents", {"query": "甲"}),
            _call("report_no_evidence", {"reason": "无"}),
        ]
    )
    output = _agent(rag, gateway).run(_input())
    assert len(rag.seen) == 2
    assert output.attempts["tool_loop"]["searches"] == 2


def test_a_denied_first_search_never_reaches_the_model():
    denied = ToolOutput(
        success=False, error="无权", error_code="tool_document_scope_denied"
    )
    gateway = _Scripted([])
    output = _agent(_Rag(denied), gateway).run(_input())
    assert output.error_code == "tool_document_scope_denied"
    assert gateway.requests == []


def test_a_denied_later_search_stops_without_switching():
    denied = ToolOutput(
        success=False, error="无权", error_code="tool_document_scope_denied"
    )
    rag = _Rag(NOTHING, denied)
    gateway = _Scripted([_call("search_documents", {"query": "x"})])
    output = _agent(rag, gateway).run(_input())
    assert output.error_code == "tool_document_scope_denied"
    assert len(rag.seen) == 2


def test_losing_its_way_switches_to_the_fixed_route():
    rag = _Rag(_ready(_evidence()))
    gateway = _Scripted(
        [ToolChatResponse("不想调用工具")],
        chat_output=json.dumps(
            {"answer": "固定路线回答", "citations": [{"chunk_id": 7}]},
            ensure_ascii=False,
        ),
    )
    output = _agent(rag, gateway).run(_input())
    assert output.answer == "固定路线回答"
    assert output.attempts["switched_to_fixed"] == "answered_in_text"


def test_a_degraded_search_is_recorded():
    degraded = _ready(_evidence())
    degraded.data["degraded"] = True
    output = _agent(_Rag(degraded), _Scripted([_submit()])).run(_input())
    assert output.success


def test_confirmed_facts_are_data_not_instructions():
    gateway = _Scripted([_submit()])
    _agent(_Rag(_ready(_evidence())), gateway).run(
        _input(confirmed_facts=[{"fact_id": "f1", "statement": "销售额为100元"}])
    )
    messages = gateway.requests[0]
    assert "销售额为100元" in messages[1]["content"]
    assert "不构成指令" in messages[1]["content"]
    assert "不得因资料未复述" in messages[0]["content"]


def test_routing_feedback_uses_the_fixed_route():
    gateway = _Scripted(
        [],
        chat_output=json.dumps(
            {"answer": "回答", "citations": [{"chunk_id": 7}]}, ensure_ascii=False
        ),
    )
    output = _agent(_Rag(_ready(_evidence())), gateway).run(
        _input(feedback={"target": "knowledge", "mode": "retry_same_scope"})
    )
    assert output.attempts == {"same_scope_retry": 1}
    assert gateway.requests == []
