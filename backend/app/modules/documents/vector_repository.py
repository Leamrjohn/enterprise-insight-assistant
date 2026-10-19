"""向量搜索 Repository

提供基于 pgvector 的语义搜索功能。
需要 PostgreSQL 安装了 pgvector 扩展才能运行。
"""

import re

from app.modules.documents.chunks import DocumentChunk
from sqlalchemy import text
from sqlalchemy.orm import Session


def _character_bigrams(text_value: str) -> set[str]:
    normalized = "".join(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", text_value.lower()))
    return {normalized[index : index + 2] for index in range(len(normalized) - 1)}


def _hybrid_score(question: str, content: str, vector_score: float) -> float:
    question_bigrams = _character_bigrams(question)
    content_bigrams = _character_bigrams(content)
    overlap = len(question_bigrams & content_bigrams) / max(len(question_bigrams), 1)
    return 0.75 * vector_score + 0.25 * overlap


def search_similar_chunks(
    db: Session,
    embedding: list[float],
    company_id: int,
    question: str = "",
    top_k: int = 5,
    min_score: float = 0.5,
    document_ids: list[int] | None = None,
    chunk_strategy: str = "paragraph_v1",
) -> list[dict]:
    """搜索与给定向量最相似的文档分块

    参数：
        db: 数据库会话
        embedding: 查询向量（384 维）
        company_id: 公司 ID（用于租户过滤）
        top_k: 返回前几条结果
        min_score: 最低相似度阈值

    返回：
        [{chunk_id, document_id, content, page_number, score}, ...]
    """
    embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"

    scope_filter = (
        "AND dc.document_id = ANY(:document_ids)" if document_ids is not None else ""
    )
    candidate_limit = min(max(top_k * 5, top_k), 50)
    sql = text(f"""
        SELECT
            dc.id AS chunk_id,
            dc.document_id,
            dc.content,
            dc.page_number,
            dc.paragraph_start,
            dc.paragraph_end,
            dc.chunk_strategy,
            d.name AS document_name,
            d.file_type AS document_type,
            1 - (dc.embedding <=> :embedding) AS score
        FROM document_chunks dc
        JOIN documents d ON d.id = dc.document_id
        WHERE
            dc.company_id = :company_id
            AND d.company_id = :company_id
            AND dc.chunk_strategy = :chunk_strategy
            AND 1 - (dc.embedding <=> :embedding) > :min_score
            {scope_filter}
        ORDER BY dc.embedding <=> :embedding
        LIMIT :candidate_limit
    """)

    rows = db.execute(
        sql,
        {
            "embedding": embedding_str,
            "company_id": company_id,
            "min_score": min_score,
            "candidate_limit": candidate_limit,
            "document_ids": document_ids,
            "chunk_strategy": chunk_strategy,
        },
    ).fetchall()

    candidates = [
        {
            "chunk_id": row.chunk_id,
            "document_id": row.document_id,
            "content": row.content,
            "page_number": row.page_number,
            "paragraph_start": row.paragraph_start,
            "paragraph_end": row.paragraph_end,
            "chunk_strategy": row.chunk_strategy,
            "document_name": row.document_name,
            "document_type": row.document_type,
            "score": round(float(row.score), 4),
        }
        for row in rows
    ]
    return sorted(
        candidates,
        key=lambda row: _hybrid_score(question, row["content"], row["score"]),
        reverse=True,
    )[:top_k]


def delete_embeddings_by_document(db: Session, document_id: int) -> None:
    """删除文档的所有向量（删除文档时同步调用）"""
    db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).update(
        {DocumentChunk.embedding: None}
    )
    db.commit()
