"""Document retrieval and reranking."""

from __future__ import annotations

from typing import Literal

from pydantic import field_validator

from app.core.config.base import ConfigDomain, require_positive, require_score


class RagConfig(ConfigDomain):
    reranker_model: str = "BAAI/bge-reranker-base"
    rag_retrieval_policy: Literal[
        "paragraph_jieba_rrf_rerank_v1", "passage_jieba_rrf_rerank_v1"
    ] = "paragraph_jieba_rrf_rerank_v1"
    rag_retrieval_top_k: int = 10
    rag_retrieval_min_score: float = 0.1
    rag_rerank_top_k: int = 3
    rag_rerank_min_score: float = 0.5
    # Reciprocal rank fusion constant; a larger value flattens rank differences.
    rag_rrf_k: int = 60

    @field_validator("rag_retrieval_top_k", "rag_rerank_top_k", "rag_rrf_k")
    @classmethod
    def rag_validate_positive_int(cls, value: int) -> int:
        return require_positive(value)

    @field_validator("rag_retrieval_min_score", "rag_rerank_min_score")
    @classmethod
    def rag_validate_score(cls, value: float) -> float:
        return require_score(value)
