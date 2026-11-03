"""The tool loop's limits hold whatever the model writes."""

import json

from app.core.exceptions import PermanentModelError, RetryableModelError
from app.core.gateway.base import ModelGateway, ToolCall, ToolChatResponse
from app.modules.runtime.tool_loop import (
    LoopLimits,
    ToolReply,
    ToolSpec,
    run_tool_loop,
)
from pydantic import BaseModel, ConfigDict


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: int


SPEC = ToolSpec(
    name="probe",
    version="probe/v1",
    purpose="探测",
    when_to_use="需要时",
    when_not_to_use="不需要时",
    example={"value": 1},
    common_errors=("value 必须是整数",),
    input_model=_Args,
)


def _call(arguments='{"value": 1}', name="probe", call_id="c1"):
    return ToolChatResponse(None, (ToolCall(call_id, name, arguments),))


class _Scripted(ModelGateway):
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def chat(self, prompt, system_prompt=None, *, json_mode=False):
        raise AssertionError("not used")

    def chat_with_tools(self, messages, tools, *, tool_choice="auto"):
        self.requests.append([dict(m) for m in messages])
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def count_tokens(self, text):
        return len(text)


def _run(responses, reply=None, limits=None, clock=None):
    gateway = _Scripted(responses)
    seen = []

    def handler(args):
        seen.append(args)
        return reply(args) if callable(reply) else (reply or ToolReply({"ok": True}))

    kwargs = {"clock": clock} if clock else {}
    result = run_tool_loop(
        gateway,
        system_prompt="s",
        user_prompt="u",
        specs=[SPEC],
        handlers={"probe": handler},
        limits=limits or LoopLimits(backoff_seconds=0),
        sleep=lambda _s: None,
        **kwargs,
    )
    return result, gateway, seen


def _tool_contents(gateway):
    return [
        json.loads(m["content"]) for m in gateway.requests[-1] if m["role"] == "tool"
    ]


def test_the_catalog_tells_the_model_when_to_use_and_when_not():
    function = SPEC.to_openai()["function"]
    assert "何时用" in function["description"]
    assert "何时不用" in function["description"]
    assert "常见错误" in function["description"]
    assert function["parameters"]["properties"]["value"]["type"] == "integer"


def test_a_finishing_handler_ends_the_loop():
    result, gateway, _ = _run([_call()], reply=ToolReply({"done": True}, "finish"))
    assert result.stop_reason == "finished"
    assert len(gateway.requests) == 1


def test_stopping_with_text_is_reported_as_such():
    result, _, _ = _run([_call(), ToolChatResponse("回答")])
    assert result.stop_reason == "answered_in_text"
    assert result.text == "回答"


def test_a_bad_argument_goes_back_to_the_model_without_reaching_the_handler():
    result, gateway, seen = _run([_call('{"value": "x"}'), ToolChatResponse("回答")])
    assert seen == []
    assert result.trace[0]["error_code"] == "tool_arguments_invalid"
    assert "value" in _tool_contents(gateway)[0]["problems"][0]


def test_invalid_json_goes_back_to_the_model():
    result, _, _ = _run([_call("{not json"), ToolChatResponse("回答")])
    assert result.trace[0]["error_code"] == "tool_arguments_not_json"


def test_an_invented_argument_is_refused():
    result, _, seen = _run(
        [_call('{"value": 1, "company_id": 9}'), ToolChatResponse("回答")]
    )
    assert seen == []
    assert result.trace[0]["error_code"] == "tool_arguments_invalid"


def test_an_unknown_tool_is_refused_and_named_alternatives_returned():
    result, gateway, _ = _run([_call(name="drop_table"), ToolChatResponse("回答")])
    assert result.trace[0]["error_code"] == "tool_unknown"
    assert _tool_contents(gateway)[0]["available"] == ["probe"]


def test_the_same_error_twice_is_no_progress():
    reply = ToolReply({"error": "字段不存在"}, "repairable", "sql_validation_error")
    result, _, seen = _run([_call(), _call(), _call()], reply=reply)
    assert result.stop_reason == "no_progress"
    assert len(seen) == 2


def test_different_errors_still_stop_after_the_repair_ceiling():
    count = iter(range(10))

    def reply(_args):
        return ToolReply({"error": f"错误{next(count)}"}, "repairable", "code")

    result, _, seen = _run([_call()] * 5, reply=reply)
    assert result.stop_reason == "no_progress"
    assert len(seen) == 3


def test_a_denial_stops_at_once_and_is_not_retried():
    reply = ToolReply({"error": "无权"}, "denied", "tool_company_scope_denied")
    result, gateway, seen = _run([_call(), _call()], reply=reply)
    assert result.stop_reason == "denied"
    assert len(seen) == 1
    assert len(gateway.requests) == 1


def test_an_exhausted_budget_stops_at_once():
    reply = ToolReply({"error": "用完"}, "exhausted", "tool_budget_exhausted")
    result, _, _ = _run([_call(), _call()], reply=reply)
    assert result.stop_reason == "exhausted"


def test_rounds_are_capped():
    result, gateway, _ = _run(
        [_call()] * 10, limits=LoopLimits(max_rounds=3, max_tool_calls=99)
    )
    assert result.stop_reason == "limit_reached"
    assert len(gateway.requests) == 3


def test_tool_calls_are_capped_even_when_one_round_asks_for_many():
    many = ToolChatResponse(
        None, tuple(ToolCall(f"c{i}", "probe", '{"value": 1}') for i in range(9))
    )
    result, _, seen = _run([many], limits=LoopLimits(max_tool_calls=4))
    assert result.stop_reason == "limit_reached"
    assert len(seen) == 4


def test_time_is_capped():
    times = iter([0.0, 1.0, 1000.0])
    result, gateway, _ = _run([_call()] * 3, clock=lambda: next(times))
    assert result.stop_reason == "limit_reached"
    assert len(gateway.requests) == 1


def test_a_temporary_model_failure_is_retried_by_code():
    result, gateway, _ = _run(
        [RetryableModelError("x"), _call(), ToolChatResponse("回答")]
    )
    assert result.stop_reason == "answered_in_text"
    assert len(gateway.requests) == 3


def test_a_model_failure_that_persists_ends_the_loop():
    result, _, _ = _run([RetryableModelError("x"), RetryableModelError("x")])
    assert result.stop_reason == "model_error"


def test_a_permanent_model_failure_is_not_retried():
    result, gateway, _ = _run([PermanentModelError("x")])
    assert result.stop_reason == "model_error"
    assert len(gateway.requests) == 1


def test_every_call_in_a_round_gets_its_own_reply():
    both = ToolChatResponse(
        None,
        (
            ToolCall("a", "probe", '{"value": 1}'),
            ToolCall("b", "probe", '{"value": 2}'),
        ),
    )
    _, gateway, seen = _run([both, ToolChatResponse("回答")])
    ids = [m["tool_call_id"] for m in gateway.requests[-1] if m["role"] == "tool"]
    assert ids == ["a", "b"]
    assert [args.value for args in seen] == [1, 2]
