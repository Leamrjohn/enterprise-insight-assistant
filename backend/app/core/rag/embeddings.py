from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    """Embedding 提供者抽象类"""

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """将文本转换为向量"""
        ...
