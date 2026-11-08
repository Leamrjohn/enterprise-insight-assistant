from datetime import date

from app.core.exceptions import EmbeddingError, VectorSearchError
from app.modules.documents.chunks import DocumentChunk
from app.modules.documents.search_tokens import TOKENIZERS
from app.modules.documents.vector_repository import (
    search_keyword_chunks,
    search_similar_chunks,
)
from app.modules.knowledge.rag.embeddings import EmbeddingProvider
from app.modules.knowledge.rag.engine import EvidenceRef
from app.modules.knowledge.rag.validity import ValidityWindow
from app.utils.document_chunk import SUPPORTED_CHUNK_STRATEGIES
from sqlalchemy import select
from sqlalchemy.orm import Session

RRF_K = 60  # the standard constant; a larger value flattens rank differences


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


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
    validity: ValidityWindow | None = None,
    keyword_tokenizer: str | None = None,
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
        valid_between = (validity.start, validity.end) if validity else None
        keyword_tokens = (
            TOKENIZERS[keyword_tokenizer](question) if keyword_tokenizer else []
        )
        # One ranked list per route, labelled with how it found its chunks.
        routes: list[tuple[str, list[dict]]] = []
        for strategy in chunk_strategies:
            routes.append(
                (
                    strategy,
                    search_similar_chunks(
                        db=db,
                        embedding=embedding,
                        company_id=company_id,
                        question=question,
                        top_k=top_k,
                        min_score=min_score,
                        document_ids=document_ids,
                        chunk_strategy=strategy,
                        valid_between=valid_between,
                    ),
                )
            )
            if keyword_tokenizer:
                routes.append(
                    (
                        f"keyword:{strategy}",
                        search_keyword_chunks(
                            db=db,
                            tokens=keyword_tokens,
                            embedding=embedding,
                            company_id=company_id,
                            top_k=top_k,
                            document_ids=document_ids,
                            chunk_strategy=strategy,
                            valid_between=valid_between,
                        ),
                    )
                )
    except Exception as exc:
        raise VectorSearchError("Failed to search document vectors") from exc
    if len(routes) == 1:
        label, rows = routes[0]
        return [_evidence(row, (label,)) for row in rows]
    return _fuse_routes(routes)[:top_k]


def _evidence(row: dict, labels: tuple[str, ...]) -> EvidenceRef:
    return EvidenceRef(
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
        retrieval_strategies=labels,
        effective_from=_iso(row.get("effective_from")),
        effective_to=_iso(row.get("effective_to")),
        applies_to=row.get("applies_to"),
    )


def _fuse_routes(routes: list[tuple[str, list[dict]]]) -> list[EvidenceRef]:
    """Reciprocal rank fusion: rank position decides, so routes with different
    score scales can be combined.  Text found twice counts as one chunk."""
    fused: dict[tuple[int, str], dict] = {}
    for label, rows in routes:
        for rank, row in enumerate(rows, start=1):
            key = (row["document_id"], " ".join(row["content"].split()))
            entry = fused.setdefault(key, {"row": row, "labels": [], "rrf": 0.0})
            entry["rrf"] += 1 / (RRF_K + rank)
            entry["labels"].append(label)
            if float(row["score"]) > float(entry["row"]["score"]):
                entry["row"] = row
    ranked = sorted(
        fused.values(),
        key=lambda entry: (entry["rrf"], entry["row"]["score"]),
        reverse=True,
    )
    return [_evidence(entry["row"], tuple(entry["labels"])) for entry in ranked]
