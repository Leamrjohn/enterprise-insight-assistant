"""Embedding 提供者抽象

作用：把文字转换成向量（数字列表）。
当前实现使用本地模型（sentence-transformers），
后续可以换成 OpenAI 或其他模型而不改调用代码。
"""

from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    """向量生成器的抽象接口"""

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """把单段文字转成向量"""
        ...

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """批量把多段文字转成向量（比循环调 embed 更快）"""
        ...
