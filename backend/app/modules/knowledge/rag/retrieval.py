from app.core.exceptions import EmbeddingError, VectorSearchError
from app.modules.documents.chunks import DocumentChunk
from app.modules.documents.vector_repository import search_similar_chunks
from app.modules.knowledge.rag.embeddings import EmbeddingProvider
from app.modules.knowledge.rag.engine import EvidenceRef
from app.utils.document_chunk import SUPPORTED_CHUNK_STRATEGIES
from sqlalchemy import select
from sqlalchemy.orm import Session


def retrieve_evidence(
    db: Session,
    question: str,
    company_id: int,
    embedder: EmbeddingProvider,
    *,
    top_k: int = 10,
    min_score: float = 0.3,
    document_ids: list[int] | None = None,
    chunk_strategies: tuple[str, ...] = ("paragraph_v1",),
) -> list[EvidenceRef]:
    """为指定公司内已冻结的文档范围检索证据。"""
    if not question.strip():
        raise ValueError("question must not be empty")
    if (
        not chunk_strategies
        or len(set(chunk_strategies)) != len(chunk_strategies)
        or not set(chunk_strategies).issubset(SUPPORTED_CHUNK_STRATEGIES)
    ):
        raise ValueError("retrieval chunk strategies are invalid")

    try:
        embedding = embedder.embed(question)
    except Exception as exc:
        raise EmbeddingError("Failed to embed retrieval question") from exc

    try:
        if document_ids is not None:
            indexed_pairs = set(
                db.execute(
                    select(DocumentChunk.document_id, DocumentChunk.chunk_strategy)
                    .where(
                        DocumentChunk.company_id == company_id,
                        DocumentChunk.document_id.in_(document_ids),
                        DocumentChunk.chunk_strategy.in_(chunk_strategies),
                    )
                    .distinct()
                ).all()
            )
            missing = [
                document_id
                for document_id in document_ids
                if any(
                    (document_id, strategy) not in indexed_pairs
                    for strategy in chunk_strategies
                )
            ]
            if missing:
                raise ValueError("retrieval chunk strategy index is incomplete")
        results = [
            row
            for strategy in chunk_strategies
            for row in search_similar_chunks(
                db=db,
                embedding=embedding,
                company_id=company_id,
                question=question,
                top_k=top_k,
                min_score=min_score,
                document_ids=document_ids,
                chunk_strategy=strategy,
            )
        ]
    except Exception as exc:
        raise VectorSearchError("Failed to search document vectors") from exc
    evidences = [
        EvidenceRef(
            chunk_id=row["chunk_id"],
            document_id=row["document_id"],
            content=row["content"],
            score=float(row["score"]),
            document_name=row.get("document_name"),
            document_type=row.get("document_type"),
            page_number=row.get("page_number"),
            paragraph_start=row.get("paragraph_start"),
            paragraph_end=row.get("paragraph_end"),
            chunk_strategy=row["chunk_strategy"],
            retrieval_strategies=(row["chunk_strategy"],),
        )
        for row in results
    ]
    if len(chunk_strategies) == 1:
        return evidences

    merged: dict[tuple[int, str], EvidenceRef] = {}
    for row, evidence in zip(results, evidences):
        key = (row["document_id"], " ".join(row["content"].split()))
        existing = merged.get(key)
        strategy = row["chunk_strategy"]
        if existing is not None:
            routes = tuple(dict.fromkeys((*existing.retrieval_strategies, strategy)))
            if existing.score >= float(row["score"]):
                existing.retrieval_strategies = routes
                continue
            evidence.retrieval_strategies = routes
        merged[key] = evidence
    return sorted(merged.values(), key=lambda evidence: evidence.score, reverse=True)[
        :top_k
    ]
