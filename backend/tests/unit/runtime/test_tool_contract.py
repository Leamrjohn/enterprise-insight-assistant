"""Stage 4.2: tool denials explain what the caller should change."""

import re
from pathlib import Path

from app.modules.runtime.tool_runtime import DENY_MESSAGES, deny_message

# Event types and field names that look like codes but are not denials.
_NOT_DENIAL_CODES = {
    "tool_started",
    "tool_completed",
    "tool_failed",
    "tool_denied",
    "tool_runtime_unexpected_error",
    "tool_contract_version",
}


def test_every_deny_code_used_by_the_runtime_has_a_specific_message() -> None:
    source = Path("app/modules/runtime/tool_runtime.py").read_text(encoding="utf-8")
    used = set(re.findall(r'"(tool_[a-z_]+)"', source)) - _NOT_DENIAL_CODES

    assert used <= set(DENY_MESSAGES)
    assert len(set(DENY_MESSAGES.values())) == len(DENY_MESSAGES)


def test_unknown_deny_code_falls_back_to_generic_message() -> None:
    assert deny_message("tool_something_new") == "工具调用不在已授权范围内。"
