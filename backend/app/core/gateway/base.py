"""Model Gateway - AI 模型调用网关

职责：
1. 统一模型调用接口（业务代码不直接依赖具体模型 SDK）
2. 记录 Token 使用和成本
3. 统一超时、重试和错误处理
4. 控制发送给模型的数据（脱敏、权限检查）
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

from app.core.exceptions import PermanentModelError


@dataclass
class ModelCallRecord:
    """一次模型调用的完整记录"""

    model_name: str
    prompt: str
    response: str | None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost: float | None = None
    success: bool = True
    error_message: str | None = None
    duration_ms: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True)
class ToolCall:
    """模型想调用的一个工具；arguments 是模型写的原始 JSON 文本，尚未校验。"""

    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class ToolChatResponse:
    """一轮工具对话的回复：要么有工具调用，要么是模型的文字回答。"""

    text: str | None
    tool_calls: tuple[ToolCall, ...] = ()

    def assistant_message(self) -> dict:
        """这轮回复放回对话历史时的格式，下一轮模型靠它对应工具结果。"""
        message: dict = {"role": "assistant", "content": self.text or ""}
        if self.tool_calls:
            message["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {"name": call.name, "arguments": call.arguments},
                }
                for call in self.tool_calls
            ]
        return message


class ToolCallingUnsupportedError(PermanentModelError):
    """当前网关没有实现原生工具调用。"""


class ModelGateway(ABC):
    """模型网关抽象类 - 所有模型提供者都要实现这个接口"""

    @abstractmethod
    def chat(
        self,
        prompt: str,
        system_prompt: str | None = None,
        *,
        json_mode: bool = False,
    ) -> str:
        """发送对话请求；json_mode 要求模型返回一个 JSON 对象。"""
        ...

    def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        *,
        tool_choice: str | dict = "auto",
    ) -> ToolChatResponse:
        """原生工具调用；没有实现的网关明确拒绝，由调用方退回固定路线。"""
        raise ToolCallingUnsupportedError(
            f"{type(self).__name__} does not support tool calling"
        )

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """计算一段文本的 Token 数量"""
        ...
