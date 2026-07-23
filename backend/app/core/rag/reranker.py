"""将向量召回的候选 chunk 按问题相关性重新排序。"""

import logging
from dataclasses import replace
from typing import Protocol

from app.core.exceptions import RerankingError
from app.core.rag.engine import EvidenceRef

logger = logging.getLogger(__name__)


class Reranker(Protocol):
    """相关性重排协议，方便在测试或后续服务化时替换实现。"""

    def score(self, question: str, passages: list[str]) -> list[float]:
        """返回与 passages 一一对应、范围为 0 到 1 的相关性分数。"""
        ...


_model = None


def _get_model(model_name: str):
    global _model
    if _model is None:
        from sentence_transformers import CrossEncoder

        logger.info("Loading reranker model: %s", model_name)
        _model = CrossEncoder(model_name)
        logger.info("Reranker model loaded")
    return _model


class LocalCrossEncoderReranker:
    """使用本地 CrossEncoder 对“问题 + chunk”进行语义相关性评分。"""

    def __init__(self, model_name: str) -> None:
        self._model_name = model_name

    def score(self, question: str, passages: list[str]) -> list[float]:
        if not passages:
            return []

        try:
            from torch.nn import Sigmoid

            scores = _get_model(self._model_name).predict(
                [(question, passage) for passage in passages],
                activation_fn=Sigmoid(),
                show_progress_bar=False,
            )
        except Exception as exc:
            raise RerankingError("Failed to rerank retrieved evidence") from exc

        return [float(score) for score in scores]


def rerank_evidences(
    question: str,
    evidences: list[EvidenceRef],
    reranker: Reranker,
    *,
    top_k: int,
) -> list[EvidenceRef]:
    """保留相关性最高的候选，并保留原始向量分数供审计。"""
    if top_k <= 0:
        raise ValueError("top_k must be positive")

    scores = reranker.score(question, [evidence.content for evidence in evidences])
    if len(scores) != len(evidences):
        raise RerankingError("Reranker score count does not match evidence count")

    reranked = [
        replace(evidence, rerank_score=score)
        for evidence, score in zip(evidences, scores)
    ]
    return sorted(
        reranked,
        key=lambda evidence: evidence.rerank_score or 0.0,
        reverse=True,
    )[:top_k]
