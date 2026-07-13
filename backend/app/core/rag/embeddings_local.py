"""本地 Embedding 实现（基于 sentence-transformers）

使用 HuggingFace 的轻量级模型，完全本地运行，不需要 API Key。
首次运行时会自动下载模型（约 80MB）。
"""

import logging
from app.core.rag.embeddings import EmbeddingProvider

logger = logging.getLogger(__name__)

# 全局缓存模型实例（避免每次调用都重新加载）
_model = None


def _get_model():
    """懒加载模型，只加载一次"""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        logger.info("Loading embedding model: all-MiniLM-L6-v2")
        _model = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("Embedding model loaded")
    return _model


class LocalEmbeddingProvider(EmbeddingProvider):
    """使用 sentence-transformers 本地模型生成向量"""

    def __init__(self):
        self._model = _get_model()

    def embed(self, text: str) -> list[float]:
        return self._model.encode(text).tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [vec.tolist() for vec in self._model.encode(texts)]
