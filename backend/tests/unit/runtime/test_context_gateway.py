"""C2 step 3: calls nobody declared are still split, by the gateway."""

import json

from app.core.tokenizer import count_tokens
from app.modules.runtime.context_measurement import context_usage, gateway_sections

TOOL_CALLS = [
    {
        "id": "call_1",
        "type": "function",
        "function": {"name": "run_sql", "arguments": '{"sql": "select 1"}'},
    }
]
TOOLS = [{"type": "function", "function": {"name": "run_sql", "parameters": {}}}]
MESSAGES = [
    {"role": "system", "content": "你是数据助手"},
    {"role": "user", "content": "华东区8月销售额？"},
    {"role": "assistant", "content": None, "tool_calls": TOOL_CALLS},
    {"role": "tool", "tool_call_id": "call_1", "content": "[[1]]"},
    {"role": "assistant", "content": "我再查一次", "tool_calls": TOOL_CALLS},
    {"role": "tool", "tool_call_id": "call_1", "content": "[[2]]"},
]


# --- plain chat: what the gateway sees is system + prompt ---------------------


def test_plain_chat_is_system_and_prompt():
    assert gateway_sections("华东区8月销售额？", "你是规划助手") == {
        "system": "你是规划助手",
        "prompt": "华东区8月销售额？",
    }


def test_no_system_prompt_still_has_the_key():
    # Same keys on every call, so one SQL query covers them all.
    assert gateway_sections("问题") == {"system": "", "prompt": "问题"}


# --- tool loop: messages grouped by role, plus the tool schemas ---------------


def test_tool_loop_groups_messages_by_role():
    sections = gateway_sections("ignored", messages=MESSAGES, tools=TOOLS)

    assert set(sections) == {"system", "user", "assistant", "tool_results", "tools"}
    assert sections["system"] == "你是数据助手"
    assert sections["user"] == "华东区8月销售额？"
    assert sections["tool_results"] == "[[1]]\n[[2]]"
    assert sections["tools"] == json.dumps(TOOLS, ensure_ascii=False)


def test_assistant_turns_count_their_tool_calls():
    calls = json.dumps(TOOL_CALLS, ensure_ascii=False)
    sections = gateway_sections("ignored", messages=MESSAGES, tools=TOOLS)

    # content None -> only the tool calls; content present -> content, then calls
    assert sections["assistant"] == f"{calls}\n我再查一次\n{calls}"


def test_empty_text_assistant_turn_is_like_none():
    # The real loop sends content "" (gateway/base.py assistant_message).
    turn = {"role": "assistant", "content": "", "tool_calls": TOOL_CALLS}
    sections = gateway_sections("ignored", messages=[*MESSAGES[:2], turn], tools=TOOLS)

    assert sections["assistant"] == json.dumps(TOOL_CALLS, ensure_ascii=False)


def test_tool_loop_prompt_is_not_counted_twice():
    # chat_with_tools passes the whole request again as `prompt`.
    sections = gateway_sections("x" * 500, messages=MESSAGES, tools=TOOLS)

    assert "prompt" not in sections
    assert "x" * 500 not in sections.values()


def test_first_round_has_empty_assistant_and_tool_results():
    sections = gateway_sections("ignored", messages=MESSAGES[:2], tools=TOOLS)

    assert sections["assistant"] == ""
    assert sections["tool_results"] == ""


# --- context_usage: declaration first, then the gateway's split ---------------


def test_fallback_is_marked_auto():
    usage = context_usage(None, {"system": "系统", "prompt": "问题"})

    assert usage == {
        "declared": "auto",
        "tokens": {
            "system": count_tokens("系统"),
            "prompt": count_tokens("问题"),
            "total": count_tokens("系统") + count_tokens("问题"),
        },
    }


def test_declaration_wins_over_fallback():
    usage = context_usage({"question": "问题"}, {"system": "系统", "prompt": "问题"})

    assert usage["declared"] is True
    assert set(usage["tokens"]) == {"question", "total"}
