"""Native tool calling through the gateways: request shape, parsing, replay."""

from types import SimpleNamespace

import pytest
from app.core.gateway.base import (
    ModelGateway,
    ToolCall,
    ToolCallingUnsupportedError,
    ToolChatResponse,
)
from app.core.gateway.deepseek import DeepSeekGateway
from app.core.gateway.replay import RecordReplayGateway, ReplayMissError

TOOLS = [{"type": "function", "function": {"name": "t", "parameters": {}}}]
MESSAGES = [{"role": "user", "content": "q"}]


def _response(content=None, calls=()):
    tool_calls = [
        SimpleNamespace(
            id=call_id, function=SimpleNamespace(name=name, arguments=arguments)
        )
        for call_id, name, arguments in calls
    ]
    message = SimpleNamespace(content=content, tool_calls=tool_calls or None)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message)],
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
    )


def _gateway(response):
    gateway = DeepSeekGateway.__new__(DeepSeekGateway)
    gateway.model_name = "deepseek-v4-flash"
    gateway.timeout_seconds = 5
    gateway.temperature = 0
    gateway.max_output_tokens = 100
    gateway.logger = SimpleNamespace(
        info=lambda *a, **k: None, error=lambda *a, **k: None
    )
    seen = {}

    def create(**kwargs):
        seen.update(kwargs)
        return response

    gateway.client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    return gateway, seen


def test_deepseek_sends_tools_and_parses_calls():
    gateway, seen = _gateway(_response(calls=[("c1", "t", '{"a": 1}')]))
    result = gateway.chat_with_tools(MESSAGES, TOOLS)
    assert seen["tools"] == TOOLS
    assert seen["tool_choice"] == "auto"
    assert seen["messages"] == MESSAGES
    assert result.tool_calls == (ToolCall("c1", "t", '{"a": 1}'),)


def test_deepseek_returns_text_when_the_model_stops_calling():
    gateway, _ = _gateway(_response(content="答案"))
    result = gateway.chat_with_tools(MESSAGES, TOOLS)
    assert result.text == "答案"
    assert result.tool_calls == ()


def test_plain_chat_still_returns_text_without_tools_in_the_request():
    gateway, seen = _gateway(_response(content="答案"))
    assert gateway.chat("q", "s") == "答案"
    assert "tools" not in seen
    assert seen["messages"][0] == {"role": "system", "content": "s"}


def test_assistant_message_keeps_the_call_ids_the_next_turn_needs():
    message = ToolChatResponse(None, (ToolCall("c1", "t", "{}"),)).assistant_message()
    assert message["tool_calls"][0]["id"] == "c1"


def test_a_gateway_without_tools_refuses_explicitly():
    class Plain(ModelGateway):
        def chat(self, prompt, system_prompt=None, *, json_mode=False):
            return ""

        def count_tokens(self, text):
            return 0

    with pytest.raises(ToolCallingUnsupportedError):
        Plain().chat_with_tools(MESSAGES, TOOLS)


def test_replay_returns_the_recording_and_fails_closed_on_a_miss(tmp_path):
    class Inner(ModelGateway):
        def chat(self, prompt, system_prompt=None, *, json_mode=False):
            return ""

        def chat_with_tools(self, messages, tools, *, tool_choice="auto"):
            return ToolChatResponse("x", (ToolCall("c1", "t", "{}"),))

        def count_tokens(self, text):
            return 0

    recorder = RecordReplayGateway(tmp_path, mode="record", inner=Inner())
    recorded = recorder.chat_with_tools(MESSAGES, TOOLS)
    replay = RecordReplayGateway(tmp_path, mode="replay")
    assert replay.chat_with_tools(MESSAGES, TOOLS) == recorded
    with pytest.raises(ReplayMissError):
        replay.chat_with_tools([{"role": "user", "content": "other"}], TOOLS)
