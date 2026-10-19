"""Server-owned retrieval profiles used for isolated RAG comparisons."""

from dataclasses import dataclass

from app.utils.document_chunk import (
    PARAGRAPH_CHUNK_STRATEGY,
    SLIDING_WINDOW_CHUNK_STRATEGY,
)


@dataclass(frozen=True)
class RetrievalPolicy:
    policy_id: str
    chunk_strategies: tuple[str, ...]
    rerank_enabled: bool

    def __post_init__(self) -> None:
        if not self.policy_id or not self.chunk_strategies:
            raise ValueError("retrieval policy requires an id and chunk strategies")
        if len(set(self.chunk_strategies)) != len(self.chunk_strategies):
            raise ValueError("retrieval policy chunk strategies must be unique")


BASELINE_RETRIEVAL_POLICY = RetrievalPolicy(
    policy_id="paragraph_vector_rerank_v1",
    chunk_strategies=(PARAGRAPH_CHUNK_STRATEGY,),
    rerank_enabled=True,
)

DUAL_CHUNK_RETRIEVAL_POLICY = RetrievalPolicy(
    policy_id="paragraph_sliding_vector_rerank_v1",
    chunk_strategies=(PARAGRAPH_CHUNK_STRATEGY, SLIDING_WINDOW_CHUNK_STRATEGY),
    rerank_enabled=True,
)
