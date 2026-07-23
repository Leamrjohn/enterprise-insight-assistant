from app.tools.protocol import Tool, ToolInput, ToolOutput
from app.core.rag.embeddings_local import LocalEmbeddingProvider
from app.core.rag.engine import build_prompt, check_sufficiency
from app.core.rag.reranker import (
    LocalCrossEncoderReranker,
    Reranker,
    rerank_evidences,
)
from app.core.rag.retrieval import retrieve_evidence
from app.core.settings import get_settings
from app.db.session import SessionLocal
from app.core.exceptions import RetrievalError
import logging

logger = logging.getLogger(__name__)


class RAGTool(Tool):
    def __init__(self, reranker: Reranker | None = None) -> None:
        self._reranker = reranker

    @property
    def name(self) -> str:
        return "rag_search"

    @property
    def description(self) -> str:
        return "在已上传的文档中搜索相关内容，用于回答需要的文档支撑的问题"

    def execute(self, input: ToolInput) -> ToolOutput:
        question = input.parameters.get("question")
        user_id = input.parameters.get("user_id")
        if not question or not user_id:
            return ToolOutput(success=False, error="缺少参数")

        db = None
        try:
            settings = get_settings()
            db = SessionLocal()
            evidences = retrieve_evidence(
                db=db,
                question=question,
                user_id=user_id,
                embedder=LocalEmbeddingProvider(),
                top_k=settings.rag_retrieval_top_k,
                min_score=settings.rag_retrieval_min_score,
            )
            reranker = self._reranker or LocalCrossEncoderReranker(
                settings.reranker_model
            )
            evidences = rerank_evidences(
                question,
                evidences,
                reranker,
                top_k=settings.rag_rerank_top_k,
            )
            if not check_sufficiency(
                evidences,
                question=question,
                min_avg_score=settings.rag_rerank_min_score,
            ):
                return ToolOutput(
                    success=True,
                    data={
                        "status": "insufficient_evidence",
                        "answer": "无法回答：资料不足",
                        "evidences": [],
                    },
                )
            system_prompt, user_prompt, allowed_chunk_ids = build_prompt(
                question, evidences
            )

            return ToolOutput(
                success=True,
                data={
                    "status": "ready",
                    "evidences": [
                        {
                            "chunk_id": evidence.chunk_id,
                            "document_id": evidence.document_id,
                            "content": evidence.content,
                            "score": evidence.score,
                            "rerank_score": evidence.rerank_score,
                        }
                        for evidence in evidences
                    ],
                    "system_prompt": system_prompt,
                    "user_prompt": user_prompt,
                    "allowed_chunk_ids": sorted(allowed_chunk_ids),
                },
            )

        except RetrievalError as exc:
            logger.warning(
                "RAG retrieval failed",
                exc_info=True,
                extra={
                    "user_id": user_id,
                    "error_type": type(exc).__name__,
                },
            )
            return ToolOutput(
                success=False,
                error="文档检索暂时不可用",
            )

        except Exception:
            logger.exception(
                "RAG tool execution failed",
                extra={"user_id": user_id},
            )
            return ToolOutput(
                success=False,
                error="RAG retrieval failed",
            )
        finally:
            if db is not None:
                db.close()
