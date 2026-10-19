import logging
import time

from app.core.exceptions import RetrievalError
from app.core.settings import get_settings
from app.db.session import SessionLocal, set_tenant_scope
from app.modules.analysis.tool_protocol import Tool, ToolInput, ToolOutput
from app.modules.knowledge.rag.embeddings_local import (
    LOCAL_EMBEDDING_MODEL_NAME,
    LocalEmbeddingProvider,
)
from app.modules.knowledge.rag.engine import build_prompt, check_sufficiency
from app.modules.knowledge.rag.policy import (
    BASELINE_RETRIEVAL_POLICY,
    RetrievalPolicy,
)
from app.modules.knowledge.rag.reranker import (
    LocalCrossEncoderReranker,
    Reranker,
    rerank_evidences,
)
from app.modules.knowledge.rag.retrieval import retrieve_evidence
from app.modules.runtime.model_governance import (
    record_model_call,
    reserve_local_resource_call,
)
from sqlalchemy import text

logger = logging.getLogger(__name__)
DEFAULT_DATABASE_TIMEOUT_MS = 10_000


class RAGTool(Tool):
    def __init__(
        self,
        reranker: Reranker | None = None,
        retrieval_policy: RetrievalPolicy = BASELINE_RETRIEVAL_POLICY,
    ) -> None:
        self._reranker = reranker
        self._retrieval_policy = retrieval_policy

    @property
    def name(self) -> str:
        return "rag_search"

    @property
    def description(self) -> str:
        return "在已上传的文档中搜索相关内容，用于回答需要的文档支撑的问题"

    def execute(self, input: ToolInput) -> ToolOutput:
        question = input.parameters.get("question")
        company_id = input.parameters.get("company_id")
        document_ids = input.parameters.get("document_ids")
        if not question or not company_id:
            return ToolOutput(success=False, error="缺少参数")
        database_timeout_ms = input.parameters.get(
            "_runtime_database_timeout_ms", DEFAULT_DATABASE_TIMEOUT_MS
        )
        if (
            not isinstance(database_timeout_ms, int)
            or isinstance(database_timeout_ms, bool)
            or not 100 <= database_timeout_ms <= 60_000
        ):
            return ToolOutput(
                success=False,
                error="检索数据库超时策略不合法。",
                error_code="rag_timeout_policy_invalid",
            )

        db = None
        try:
            settings = get_settings()
            db = SessionLocal()
            set_tenant_scope(db, company_id)
            db.execute(
                text("SELECT set_config('statement_timeout', :timeout_ms, true)"),
                {"timeout_ms": str(database_timeout_ms)},
            )
            embedding_started_at = time.perf_counter()
            embedding_scope = reserve_local_resource_call(
                resource_kind="embedding",
                model_name=LOCAL_EMBEDDING_MODEL_NAME,
                resource_usage={"input_characters": len(question)},
            )
            try:
                evidences = retrieve_evidence(
                    db=db,
                    question=question,
                    company_id=company_id,
                    embedder=LocalEmbeddingProvider(),
                    top_k=settings.rag_retrieval_top_k,
                    min_score=settings.rag_retrieval_min_score,
                    document_ids=document_ids,
                    chunk_strategies=self._retrieval_policy.chunk_strategies,
                )
            except Exception:
                record_model_call(
                    embedding_scope,
                    provider="local",
                    model_name=LOCAL_EMBEDDING_MODEL_NAME,
                    duration_ms=(time.perf_counter() - embedding_started_at) * 1000,
                    result_category="unexpected_error",
                    error_code="local_embedding_failed",
                    resource_usage={"input_characters": len(question)},
                )
                raise
            record_model_call(
                embedding_scope,
                provider="local",
                model_name=LOCAL_EMBEDDING_MODEL_NAME,
                duration_ms=(time.perf_counter() - embedding_started_at) * 1000,
                result_category="success",
                resource_usage={"input_characters": len(question)},
            )
            if self._retrieval_policy.rerank_enabled:
                reranker = self._reranker or LocalCrossEncoderReranker(
                    settings.reranker_model
                )
                rerank_started_at = time.perf_counter()
                rerank_scope = reserve_local_resource_call(
                    resource_kind="rerank",
                    model_name=settings.reranker_model,
                    resource_usage={
                        "candidate_count": len(evidences),
                        "question_characters": len(question),
                    },
                )
                try:
                    evidences = rerank_evidences(
                        question,
                        evidences,
                        reranker,
                        top_k=settings.rag_rerank_top_k,
                    )
                except Exception:
                    record_model_call(
                        rerank_scope,
                        provider="local",
                        model_name=settings.reranker_model,
                        duration_ms=(time.perf_counter() - rerank_started_at) * 1000,
                        result_category="unexpected_error",
                        error_code="local_rerank_failed",
                        resource_usage={
                            "candidate_count": len(evidences),
                            "question_characters": len(question),
                        },
                    )
                    raise
                record_model_call(
                    rerank_scope,
                    provider="local",
                    model_name=settings.reranker_model,
                    duration_ms=(time.perf_counter() - rerank_started_at) * 1000,
                    result_category="success",
                    resource_usage={
                        "candidate_count": len(evidences),
                        "question_characters": len(question),
                    },
                )
            else:
                evidences = evidences[: settings.rag_rerank_top_k]
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
                    "retrieval_policy_id": self._retrieval_policy.policy_id,
                    "evidences": [
                        {
                            "chunk_id": evidence.chunk_id,
                            "document_id": evidence.document_id,
                            "content": evidence.content,
                            "document_name": evidence.document_name,
                            "document_type": evidence.document_type,
                            "page_number": evidence.page_number,
                            "paragraph_start": evidence.paragraph_start,
                            "paragraph_end": evidence.paragraph_end,
                            "score": evidence.score,
                            "rerank_score": evidence.rerank_score,
                            "chunk_strategy": evidence.chunk_strategy,
                            "retrieval_strategies": list(evidence.retrieval_strategies),
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
                    "company_id": company_id,
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
                extra={"company_id": company_id},
            )
            return ToolOutput(
                success=False,
                error="RAG retrieval failed",
            )
        finally:
            if db is not None:
                db.close()
