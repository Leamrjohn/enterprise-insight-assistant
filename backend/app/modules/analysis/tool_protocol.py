"""工具协议 —— 所有工具必须实现这个接口"""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.modules.runtime.tools.evidence import Evidence


@dataclass
class ToolInput:
    """一次工具调用的输入"""

    parameters: dict[str, Any]


@dataclass
class ToolOutput:
    """一次工具调用的输出"""

    success: bool
    data: Any = None
    error: str | None = None
    error_code: str | None = None
    repairable: bool = False
    # Reason a model can act on. Set only for its own mistakes, never for outages.
    model_feedback: str | None = None
    # T3c: filled by ToolRuntime from the registered to_evidence; read from T3b.
    evidence: "list[Evidence] | None" = None


class Tool(ABC):
    """工具基类 —— 所有工具必须实现下面这些属性和方法"""

    @property
    @abstractmethod
    def name(self) -> str:
        """工具名称，如 'rag_search'、'sql_query'"""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """工具描述，告诉Agent这个工具能干什么"""
        ...

    @abstractmethod
    def execute(self, input: ToolInput) -> ToolOutput:
        """执行工具，输入参数，返回结果"""
        ...


class Toolset:
    """T3b: the tools one node may use, called by name.

    Nodes build it (workflow/orchestration/toolsets.py); agents only call it, so
    adding a tool to a node never changes the agent.  Unknown names are refused.
    """

    def __init__(self, tools: Mapping[str, "Tool"] = MappingProxyType({})) -> None:
        self._tools = dict(tools)

    @classmethod
    def of(cls, *tools: "Tool | None") -> "Toolset":
        return cls({tool.name: tool for tool in tools if tool is not None})

    def names(self) -> tuple[str, ...]:
        return tuple(self._tools)

    def tools(self) -> list[Tool]:
        return list(self._tools.values())

    def call(self, name: str, parameters: dict[str, Any]) -> ToolOutput:
        tool = self._tools.get(name)
        if tool is None:
            return ToolOutput(
                success=False,
                error="本节点没有这个工具。",
                error_code="tool_unknown",
            )
        return tool.execute(ToolInput(parameters=parameters))
