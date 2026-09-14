"""工具协议 —— 所有工具必须实现这个接口"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


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
