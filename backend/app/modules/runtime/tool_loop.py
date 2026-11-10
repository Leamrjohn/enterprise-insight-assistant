"""The loop that lets a model choose tools, with every limit held by code.

The model proposes a call; a handler decides what really happens and how the
outcome counts.  Scope, permissions and SQL validation stay in the handlers and
ToolRuntime, so nothing the model writes can widen them.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from app.core.config.snapshot import runtime_settings
from app.core.exceptions import PermanentModelError, RetryableModelError
from app.core.gateway.base import ModelGateway, ToolCall
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

Outcome = Literal["ok", "repairable", "denied", "exhausted", "unavailable", "finish"]
StopReason = Literal[
    "finished",  # A handler reached a final result.
    "answered_in_text",  # The model stopped calling tools.
    "no_progress",  # The same error came back twice, or repairs ran out.
    "denied",  # Permission problem: never retried, never switched.
    "exhausted",  # A task budget ran out.
    "unavailable",  # A tool's infrastructure is down, retries already spent.
    "limit_reached",  # Round, call or time ceiling.
    "model_error",  # The model service failed after code-level retries.
]


@dataclass(frozen=True)
class ToolSpec:
    """One entry of the tool catalog: what the model reads, and its parameter contract."""

    name: str
    version: str
    purpose: str
    when_to_use: str
    when_not_to_use: str
    example: dict
    common_errors: tuple[str, ...]
    input_model: type[BaseModel]

    def to_openai(self) -> dict:
        description = (
            f"{self.purpose}\n何时用：{self.when_to_use}\n"
            f"何时不用：{self.when_not_to_use}\n"
            f"示例参数：{json.dumps(self.example, ensure_ascii=False)}\n"
            f"常见错误：{'；'.join(self.common_errors)}"
        )
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": description,
                "parameters": self.input_model.model_json_schema(),
            },
        }


@dataclass(frozen=True)
class ToolReply:
    """What a handler decided: what the model sees, and how the outcome counts."""

    content: dict
    outcome: Outcome = "ok"
    error_code: str | None = None


def _setting(name: str) -> Callable[[], Any]:
    return lambda: getattr(runtime_settings(), name)


@dataclass(frozen=True)
class LoopLimits:
    """Defaults come from the TOOL_LOOP_* settings (K1)."""

    max_rounds: int = field(default_factory=_setting("tool_loop_max_rounds"))
    max_tool_calls: int = field(default_factory=_setting("tool_loop_max_tool_calls"))
    max_repairs: int = field(default_factory=_setting("tool_loop_max_repairs"))
    max_seconds: float = field(default_factory=_setting("tool_loop_max_seconds"))
    model_retries: int = field(default_factory=_setting("tool_loop_model_retries"))
    backoff_seconds: float = field(
        default_factory=_setting("tool_loop_backoff_seconds")
    )


@dataclass
class LoopResult:
    stop_reason: StopReason
    text: str | None = None
    rounds: int = 0
    trace: list[dict] = field(default_factory=list)


Handler = Callable[[BaseModel], ToolReply]
_STOP_ON_OUTCOME: dict[str, StopReason] = {
    "finish": "finished",
    "denied": "denied",
    "exhausted": "exhausted",
    "unavailable": "unavailable",
}


def _parse_arguments(call: ToolCall, spec: ToolSpec) -> BaseModel | ToolReply:
    try:
        return spec.input_model.model_validate(json.loads(call.arguments or "{}"))
    except json.JSONDecodeError:
        return ToolReply(
            {"error": "参数不是合法 JSON，请重新生成。"},
            "repairable",
            "tool_arguments_not_json",
        )
    except ValidationError as error:
        # Only where and why: the values are the model's own text and may be long.
        problems = [
            f"{'.'.join(map(str, item['loc'])) or '参数'}: {item['msg']}"
            for item in error.errors()[:5]
        ]
        return ToolReply(
            {"error": "参数不符合约定。", "problems": problems},
            "repairable",
            "tool_arguments_invalid",
        )


def _call_model(
    gateway: ModelGateway,
    messages: list[dict],
    tools: list[dict],
    limits: LoopLimits,
    sleep: Callable[[float], None],
):
    for attempt in range(limits.model_retries + 1):
        try:
            return gateway.chat_with_tools(messages, tools)
        except RetryableModelError:
            if attempt == limits.model_retries:
                raise
            sleep(limits.backoff_seconds * (2**attempt))
    raise AssertionError("unreachable")


def run_tool_loop(
    gateway: ModelGateway,
    *,
    system_prompt: str,
    user_prompt: str,
    specs: list[ToolSpec],
    handlers: dict[str, Handler],
    limits: LoopLimits | None = None,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> LoopResult:
    """Run until a handler finishes, the model stops, or a code-held limit is hit."""
    limits = limits or LoopLimits()
    by_name = {spec.name: spec for spec in specs}
    tools = [spec.to_openai() for spec in specs]
    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    result = LoopResult(stop_reason="limit_reached")
    started = clock()
    calls = 0
    repairs = 0
    seen_errors: set[tuple[str, str | None, str]] = set()

    while result.rounds < limits.max_rounds:
        if clock() - started > limits.max_seconds:
            return result
        result.rounds += 1
        try:
            response = _call_model(gateway, messages, tools, limits, sleep)
        except (RetryableModelError, PermanentModelError) as error:
            logger.warning(
                "Tool loop model call failed", extra={"error": type(error).__name__}
            )
            result.stop_reason = "model_error"
            return result
        if not response.tool_calls:
            result.stop_reason = "answered_in_text"
            result.text = response.text
            return result
        messages.append(response.assistant_message())

        for call in response.tool_calls:
            calls += 1
            spec = by_name.get(call.name)
            if spec is None:
                reply = ToolReply(
                    {"error": "没有这个工具。", "available": sorted(by_name)},
                    "repairable",
                    "tool_unknown",
                )
            elif calls > limits.max_tool_calls:
                return result
            else:
                parsed = _parse_arguments(call, spec)
                reply = (
                    parsed
                    if isinstance(parsed, ToolReply)
                    else handlers[call.name](parsed)
                )
            result.trace.append(
                {
                    "tool": call.name,
                    "outcome": reply.outcome,
                    "error_code": reply.error_code,
                }
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(reply.content, ensure_ascii=False),
                }
            )
            stop = _STOP_ON_OUTCOME.get(reply.outcome)
            if stop is not None:
                result.stop_reason = stop
                return result
            if reply.outcome == "repairable":
                fingerprint = (
                    call.name,
                    reply.error_code,
                    json.dumps(reply.content, ensure_ascii=False, sort_keys=True),
                )
                repairs += 1
                if fingerprint in seen_errors or repairs > limits.max_repairs:
                    result.stop_reason = "no_progress"
                    return result
                seen_errors.add(fingerprint)
    return result
