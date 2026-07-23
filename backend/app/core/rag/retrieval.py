from sqlalchemy.orm import Session

from app.core.rag.embeddings import EmbeddingProvider
from app.core.rag.engine import EvidenceRef
from app.repositories.vector_repository import search_similar_chunks
from app.core.exceptions import EmbeddingError, VectorSearchError

def retrieve_evidence(
    db: Session,
    question: str,
    user_id: int,
    embedder: EmbeddingProvider,
    *,
    top_k: int = 10,
    min_score: float = 0.3,
) -> list[EvidenceRef]:
    """为指定用户检索与问题相关的文档证据。"""
    if not question.strip():
        raise ValueError("question must not be empty")


    try:
        embedding = embedder.embed(question)
    except Exception as exc:
        raise EmbeddingError("Failed to embed retrieval question") from exc

    try:
        results = search_similar_chunks(
            db=db,
            embedding=embedding,
            user_id=user_id,
            top_k=top_k,
            min_score=min_score,
        )
    except Exception as exc:
        raise VectorSearchError("Failed to search document vectors") from exc
    return [
        EvidenceRef(
            chunk_id=row["chunk_id"],
            document_id=row["document_id"],
            content=row["content"],
            score=float(row["score"]),
        )
        for row in results
    ]
