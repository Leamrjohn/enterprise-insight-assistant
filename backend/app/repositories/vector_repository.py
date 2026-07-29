"""向量搜索 Repository

提供基于 pgvector 的语义搜索功能。
需要 PostgreSQL 安装了 pgvector 扩展才能运行。
"""

from sqlalchemy.orm import Session
from sqlalchemy import text
from app.models.document_chunk import DocumentChunk


def search_similar_chunks(
    db: Session,
    embedding: list[float],
    company_id: int,
    top_k: int = 5,
    min_score: float = 0.5,
    document_ids: list[int] | None = None,
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
    sql = text(f"""
        SELECT
            dc.id AS chunk_id,
            dc.document_id,
            dc.content,
            dc.page_number,
            dc.paragraph_start,
            dc.paragraph_end,
            d.name AS document_name,
            d.file_type AS document_type,
            1 - (dc.embedding <=> :embedding) AS score
        FROM document_chunks dc
        JOIN documents d ON d.id = dc.document_id
        WHERE
            dc.company_id = :company_id
            AND d.company_id = :company_id
            AND 1 - (dc.embedding <=> :embedding) > :min_score
            {scope_filter}
        ORDER BY dc.embedding <=> :embedding
        LIMIT :top_k
    """)

    rows = db.execute(
        sql,
        {
            "embedding": embedding_str,
            "company_id": company_id,
            "min_score": min_score,
            "top_k": top_k,
            "document_ids": document_ids,
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
            "document_name": row.document_name,
            "document_type": row.document_type,
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
