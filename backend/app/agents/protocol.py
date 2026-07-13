"""Agent 协议 —— 所有 Agent 必须实现这个接口"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.tools.protocol import Tool, ToolInput, ToolOutput


@dataclass
class AgentInput:
    """一次 Agent 调用的输入"""
    question: str
    user_id: int
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentOutput:
    """一次 Agent 调用的输出"""
    success: bool
    answer: str | None = None
    evidence: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


class Agent(ABC):
    """Agent 基类 —— 所有 Agent 必须实现下面这些属性和方法"""

    @property
    @abstractmethod
    def name(self) -> str:
        """Agent 名称，如 'knowledge'、'data'、'planner'、'reviewer'"""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Agent 描述，说明这个 Agent 的职责"""
        ...

    @property
    @abstractmethod
    def allowed_tools(self) -> list[Tool]:
        """这个 Agent 可以调用的工具列表"""
        ...

    @abstractmethod
    def run(self, input: AgentInput) -> AgentOutput:
        """执行 Agent，输入问题，返回结果"""
        ...
