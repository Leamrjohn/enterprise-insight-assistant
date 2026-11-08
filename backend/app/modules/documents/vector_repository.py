"""向量搜索 Repository

提供基于 pgvector 的语义搜索功能。
需要 PostgreSQL 安装了 pgvector 扩展才能运行。
"""

import re
from datetime import date

from app.modules.documents.chunks import DocumentChunk
from sqlalchemy import text
from sqlalchemy.orm import Session

MAX_KEYWORD_TOKENS = 32


def _character_bigrams(text_value: str) -> set[str]:
    normalized = "".join(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", text_value.lower()))
    return {normalized[index : index + 2] for index in range(len(normalized) - 1)}


def _hybrid_score(question: str, content: str, vector_score: float) -> float:
    question_bigrams = _character_bigrams(question)
    content_bigrams = _character_bigrams(content)
    overlap = len(question_bigrams & content_bigrams) / max(len(question_bigrams), 1)
    return 0.75 * vector_score + 0.25 * overlap


def _scope_filter(document_ids: list[int] | None) -> str:
    return "AND dc.document_id = ANY(:document_ids)" if document_ids is not None else ""


def _validity_filter(valid_between: tuple[date, date] | None) -> str:
    if valid_between is None:
        return ""
    return """AND (d.effective_from IS NULL OR d.effective_from <= :valid_end)
            AND (d.effective_to IS NULL OR d.effective_to >= :valid_start)"""


def search_similar_chunks(
    db: Session,
    embedding: list[float],
    company_id: int,
    question: str = "",
    top_k: int = 5,
    min_score: float = 0.5,
    document_ids: list[int] | None = None,
    chunk_strategy: str = "paragraph_v1",
    valid_between: tuple[date, date] | None = None,
) -> list[dict]:
    """搜索与给定向量最相似的文档分块

    参数：
        db: 数据库会话
        embedding: 查询向量（384 维）
        company_id: 公司 ID（用于租户过滤）
        top_k: 返回前几条结果
        min_score: 最低相似度阈值
        valid_between: 只保留在这段时间内有效的文档；未登记有效期的文档不过滤

    返回：
        [{chunk_id, document_id, content, page_number, score}, ...]
    """
    embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"

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
            d.effective_from,
            d.effective_to,
            d.applies_to,
            1 - (dc.embedding <=> :embedding) AS score
        FROM document_chunks dc
        JOIN documents d ON d.id = dc.document_id
        WHERE
            dc.company_id = :company_id
            AND d.company_id = :company_id
            AND dc.chunk_strategy = :chunk_strategy
            AND 1 - (dc.embedding <=> :embedding) > :min_score
            {_scope_filter(document_ids)}
            {_validity_filter(valid_between)}
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
            "valid_start": valid_between[0] if valid_between else None,
            "valid_end": valid_between[1] if valid_between else None,
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
            "effective_from": row.effective_from,
            "effective_to": row.effective_to,
            "applies_to": row.applies_to,
            "score": round(float(row.score), 4),
        }
        for row in rows
    ]
    return sorted(
        candidates,
        key=lambda row: _hybrid_score(question, row["content"], row["score"]),
        reverse=True,
    )[:top_k]


def search_keyword_chunks(
    db: Session,
    tokens: list[str],
    embedding: list[float],
    company_id: int,
    top_k: int = 10,
    document_ids: list[int] | None = None,
    chunk_strategy: str = "paragraph_v1",
    valid_between: tuple[date, date] | None = None,
) -> list[dict]:
    """全文检索：任一词命中即入选，按相关度排序；过滤条件与向量检索相同。

    分数仍然是向量相似度，这样后面的充分性判断不会看到两种尺度的分数。
    """
    unique_tokens = list(dict.fromkeys(tokens))[:MAX_KEYWORD_TOKENS]
    if not unique_tokens:
        return []
    sql = text(f"""
        WITH query AS (SELECT to_tsquery('simple', :tsquery) AS q)
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
            d.effective_from,
            d.effective_to,
            d.applies_to,
            COALESCE(1 - (dc.embedding <=> :embedding), 0) AS score
        FROM document_chunks dc
        JOIN documents d ON d.id = dc.document_id
        CROSS JOIN query
        WHERE
            dc.company_id = :company_id
            AND d.company_id = :company_id
            AND dc.chunk_strategy = :chunk_strategy
            AND dc.search_vector @@ query.q
            {_scope_filter(document_ids)}
            {_validity_filter(valid_between)}
        ORDER BY ts_rank(dc.search_vector, query.q, 1) DESC, dc.id
        LIMIT :top_k
    """)
    rows = db.execute(
        sql,
        {
            # Tokens contain only letters and digits, so quoting them is safe.
            "tsquery": " | ".join(f"'{token}'" for token in unique_tokens),
            "embedding": "[" + ",".join(str(v) for v in embedding) + "]",
            "company_id": company_id,
            "chunk_strategy": chunk_strategy,
            "document_ids": document_ids,
            "valid_start": valid_between[0] if valid_between else None,
            "valid_end": valid_between[1] if valid_between else None,
            "top_k": top_k,
        },
    ).fetchall()
    return [
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
            "effective_from": row.effective_from,
            "effective_to": row.effective_to,
            "applies_to": row.applies_to,
            "score": round(float(row.score), 4),
        }
        for row in rows
    ]


def delete_embeddings_by_document(db: Session, document_id: int) -> None:
    """删除文档的所有向量（删除文档时同步调用）"""
    db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).update(
        {DocumentChunk.embedding: None}
    )
    db.commit()
