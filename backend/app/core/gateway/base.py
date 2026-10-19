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

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """计算一段文本的 Token 数量"""
        ...
