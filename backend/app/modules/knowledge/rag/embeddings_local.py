"""本地 Embedding 实现（基于 sentence-transformers）

使用 HuggingFace 的轻量级模型，完全本地运行，不需要 API Key。
首次运行时会自动下载模型（约 80MB）。
"""

import logging

from app.modules.knowledge.rag.embeddings import EmbeddingProvider

logger = logging.getLogger(__name__)

# 全局缓存模型实例（避免每次调用都重新加载）
_model = None
LOCAL_EMBEDDING_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"


def _get_model():
    """懒加载模型，只加载一次"""
    global _model
    if _model is None:
        from sentence_transformers import (  # pyright: ignore[reportMissingImports]
            SentenceTransformer,
        )

        # The corpus and user questions are primarily Chinese.  Keep the 384-d
        # output contract required by the existing pgvector column while using
        # a multilingual encoder rather than an English-only MiniLM model.
        logger.info("Loading embedding model: %s", LOCAL_EMBEDDING_MODEL_NAME)
        _model = SentenceTransformer(LOCAL_EMBEDDING_MODEL_NAME)
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
