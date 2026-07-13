import logging
from app.core.celery_app import celery_app
from app.db.session import SessionLocal
from app.repositories.task_repository import get_task_by_id
from app.models.analysis_task import AnalysisTask
# 导入所有模型确保 SQLAlchemy 能解析外键
from app.models.user import User  # noqa: F401
from app.models.documents import Documents  # noqa: F401
from app.models.document_chunk import DocumentChunk  # noqa: F401
from app.core.model_gateway_local import LocalModelGateway
from app.core.rag_engine import (
    EvidenceRef,
    build_prompt,
    check_sufficiency,
)
from app.core.embeddings_local import LocalEmbeddingProvider
from app.repositories.vector_repository import search_similar_chunks

logger = logging.getLogger(__name__)


# 模块级网关实例（只创建一次）
_gateway = None


def _get_gateway():
    global _gateway
    if _gateway is None:
        _gateway = LocalModelGateway()
    return _gateway


# 模块级 Embedding Provider（只创建一次）
_embedder = None


def _get_embedder():
    global _embedder
    if _embedder is None:
        _embedder = LocalEmbeddingProvider()
    return _embedder


def _search_evidence(db, question: str, user_id: int) -> list[EvidenceRef]:
    """检索相关证据（使用 pgvector 向量搜索）"""
    embedder = _get_embedder()
    embedding = embedder.embed(question)

    results = search_similar_chunks(
        db=db,
        embedding=embedding,
        user_id=user_id,
        top_k=3,
        min_score=0.3,
    )

    return [
        EvidenceRef(
            chunk_id=r["chunk_id"],
            document_id=r["document_id"],
            content=r["content"],
            score=r["score"],
        )
        for r in results
    ]


@celery_app.task(bind=True, max_retries=3, default_retry_delay=5)
def process_analysis_task(self, task_id: int, user_id: int):
    """异步处理分析任务（使用 RAG 引擎）"""
    db = SessionLocal()
    try:
        # 1. 把状态改为 running
        record = db.query(AnalysisTask).filter(AnalysisTask.id == task_id).first()
        if record is None:
            logger.error(f"Task {task_id} not found")
            return

        record.status = "running"
        db.commit()

        # 2. RAG 流程：检索证据
        logger.info(f"Searching evidence for task {task_id}")
        evidences = _search_evidence(db, record.question, user_id)

        # 3. 判断证据是否充分
        if not check_sufficiency(evidences, question=record.question, min_evidences=1, min_avg_score=0.4):
            logger.warning(f"Task {task_id}: insufficient evidence")
            record.status = "completed"
            record.result_summary = "无法回答：未找到足够的资料来回答该问题"
            db.commit()
            return

        # 4. 组装 Prompt 并调用模型
        logger.info(f"Building RAG prompt for task {task_id}")
        system_prompt, user_prompt = build_prompt(record.question, evidences)
        gateway = _get_gateway()
        result = gateway.chat(prompt=user_prompt, system_prompt=system_prompt)


        # 5. 更新为 completed
        record.status = "completed"
        record.result_summary = result
        db.commit()
        db.refresh(record)

        logger.info(f"Task {task_id} completed")

    except Exception as exc:
        db.rollback()
        logger.exception(f"Task {task_id} failed")

        # 把状态改为 failed
        record = db.query(AnalysisTask).filter(AnalysisTask.id == task_id).first()
        if record is not None:
            record.status = "failed"
            record.error_message = str(exc)
            db.commit()

        raise self.retry(exc=exc)

    finally:
        db.close()
