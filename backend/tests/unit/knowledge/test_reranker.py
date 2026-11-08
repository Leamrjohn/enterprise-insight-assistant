import pytest
from app.core.exceptions import RerankingError
from app.modules.knowledge.rag.engine import EvidenceRef, check_sufficiency
from app.modules.knowledge.rag.reranker import rerank_evidences


class FakeReranker:
    def __init__(self, scores: list[float]) -> None:
        self.scores = scores

    def score(self, question: str, passages: list[str]) -> list[float]:
        return self.scores


def test_reranker_sorts_candidates_and_preserves_vector_score() -> None:
    evidences = [
        EvidenceRef(chunk_id=1, document_id=1, content="弱相关", score=0.92),
        EvidenceRef(chunk_id=2, document_id=1, content="强相关", score=0.61),
    ]

    result = rerank_evidences(
        "华东销售为何下降", evidences, FakeReranker([0.12, 0.91]), top_k=1
    )

    assert [evidence.chunk_id for evidence in result] == [2]
    assert result[0].score == 0.61
    assert result[0].rerank_score == 0.91


def test_reranker_rejects_incomplete_score_output() -> None:
    evidences = [EvidenceRef(chunk_id=1, document_id=1, content="资料", score=0.8)]

    with pytest.raises(RerankingError, match="score count"):
        rerank_evidences("问题", evidences, FakeReranker([]), top_k=1)


def test_sufficiency_uses_rerank_score_instead_of_vector_score() -> None:
    evidence = EvidenceRef(
        chunk_id=1,
        document_id=1,
        content="表面相似但不能回答问题的资料",
        score=0.95,
        rerank_score=0.12,
    )

    assert check_sufficiency([evidence], min_avg_score=0.5) is False
