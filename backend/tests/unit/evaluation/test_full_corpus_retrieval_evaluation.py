"""Real vector-retrieval regression over every corpus artifact.

This deliberately scores document retrieval only.  A hit means the intended
document contributes at least one Top-K chunk; it does not establish that an
LLM answer is factually correct or that a causal conclusion is justified.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from time import perf_counter

import pytest
from app.core.settings import get_settings
from app.db.session import set_tenant_scope
from app.modules.documents.chunks import DocumentChunk
from app.modules.documents.models import Documents
from app.modules.knowledge.rag.embeddings_local import LocalEmbeddingProvider
from app.modules.knowledge.rag.engine import check_sufficiency
from app.modules.knowledge.rag.policy import (
    BASELINE_RETRIEVAL_POLICY,
    DUAL_CHUNK_RETRIEVAL_POLICY,
    RetrievalPolicy,
)
from app.modules.knowledge.rag.reranker import (
    LocalCrossEncoderReranker,
    rerank_evidences,
)
from app.modules.knowledge.rag.retrieval import retrieve_evidence
from app.modules.knowledge.schemas import RetrievalBrief
from app.modules.organizations.models import Company
from app.utils.document_chunk import (
    PARAGRAPH_CHUNK_STRATEGY,
    SLIDING_WINDOW_CHUNK_STRATEGY,
    chunk_text_for_strategy,
)

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(
        os.getenv("RUN_FULL_CORPUS_RAG_EVAL") != "1",
        reason="set RUN_FULL_CORPUS_RAG_EVAL=1 to embed and evaluate all documents",
    ),
]


WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
CORPUS_ROOT = WORKSPACE_ROOT / "data" / "business_knowledge_base"


def _load_cases() -> list[tuple[str, str]]:
    manifest = json.loads((CORPUS_ROOT / "manifest.json").read_text(encoding="utf-8"))
    cases: list[tuple[str, str]] = []
    for artifact in manifest["artifacts"]:
        relative_path = artifact["path"]
        content = (CORPUS_ROOT / relative_path).read_text(encoding="utf-8")
        question = _business_question(relative_path, content)
        cases.append((relative_path, question))
    return cases


def _business_question(relative_path: str, content: str) -> str:
    """Create a business request without repeating a document title or path."""
    customer = re.search(r"\*\*客户名称：\*\*\s*([^（\n]+)", content)
    supplier = re.search(r"\*\*供应商(?:名称)?：\*\*\s*([^（\n]+)", content)
    period = re.search(r"(?:报告期间|数据期间)[：:]\s*([^\n]+)", content)
    if customer:
        return f"请说明客户{customer.group(1).strip()}的经营风险、沟通情况和后续建议。"
    if supplier:
        return f"请说明供应商{supplier.group(1).strip()}的履约或质量风险及处置建议。"
    if period:
        return f"请总结{period.group(1).strip()}期间的经营指标、异常和风险。"
    category = relative_path.split("/", maxsplit=1)[0]
    return f"请查找与{category}经营风险、指标变化或改进措施相关的内部资料。"


def _split(relative_path: str) -> str:
    """A stable held-out partition based only on source identity."""
    return (
        "heldout"
        if int(hashlib.sha256(relative_path.encode()).hexdigest(), 16) % 5 == 0
        else "dev"
    )


def _comparison_profiles() -> tuple[RetrievalPolicy, ...]:
    return (
        BASELINE_RETRIEVAL_POLICY,
        RetrievalPolicy(
            policy_id="paragraph_vector_no_rerank_v1",
            chunk_strategies=(PARAGRAPH_CHUNK_STRATEGY,),
            rerank_enabled=False,
        ),
        DUAL_CHUNK_RETRIEVAL_POLICY,
    )


def _development_cases(
    cases: list[tuple[str, str]], limit: int
) -> list[tuple[str, str]]:
    selected = [case for case in cases if _split(case[0]) == "dev"][:limit]
    if len(selected) != limit:
        raise ValueError("not enough development retrieval cases")
    return selected


def _profile_metrics(
    *,
    db_session,
    cases: list[tuple[str, str]],
    company_id: int,
    document_ids: dict[str, int],
    embedder: LocalEmbeddingProvider,
    policy: RetrievalPolicy,
    reranker: LocalCrossEncoderReranker,
    top_k: int,
    rerank_top_k: int,
    min_rerank_score: float,
) -> dict[str, float | int | str]:
    started = perf_counter()
    hits = 0
    reciprocal_rank = 0.0
    candidate_scope_correct = 0
    no_refusal = 0
    rerank_k = rerank_top_k
    for relative_path, question in cases:
        evidences = retrieve_evidence(
            db_session,
            question,
            company_id,
            embedder,
            top_k=top_k,
            min_score=-1.0,
            document_ids=list(document_ids.values()),
            chunk_strategies=policy.chunk_strategies,
        )
        if policy.rerank_enabled:
            evidences = rerank_evidences(
                question,
                evidences,
                reranker,
                top_k=rerank_top_k,
            )
        else:
            evidences = evidences[:rerank_top_k]
        rank = next(
            (
                index
                for index, evidence in enumerate(evidences, start=1)
                if evidence.document_id == document_ids[relative_path]
            ),
            None,
        )
        if rank is not None:
            hits += 1
            reciprocal_rank += 1.0 / rank
        candidate_scope_correct += int(
            all(evidence.document_id in document_ids.values() for evidence in evidences)
        )
        no_refusal += int(
            check_sufficiency(
                evidences,
                question=question,
                min_avg_score=min_rerank_score,
            )
        )
    elapsed_ms = round((perf_counter() - started) * 1000)
    return {
        "profile_id": policy.policy_id,
        "cases": len(cases),
        f"recall_at_{rerank_k}": hits / len(cases),
        f"mrr_at_{rerank_k}": reciprocal_rank / len(cases),
        "candidate_evidence_scope_rate": candidate_scope_correct / len(cases),
        "non_refusal_rate": no_refusal / len(cases),
        "duration_ms": elapsed_ms,
        "local_model_cost": "unknown",
    }


def test_full_corpus_vector_retrieval_covers_every_document(
    db_session, test_user
) -> None:
    """Measure Top-10 recall and MRR for at least 100 real corpus questions."""
    cases = _load_cases()
    assert len(cases) >= 100

    company = Company(name="full-corpus-retrieval-evaluation")
    db_session.add(company)
    db_session.flush()
    set_tenant_scope(db_session, company.id)

    document_ids: dict[str, int] = {}
    chunk_rows: list[DocumentChunk] = []
    chunk_texts: list[str] = []
    chunk_metadata: list[tuple[int, str, int, str, int, int]] = []
    for relative_path, _ in cases:
        content = (CORPUS_ROOT / relative_path).read_text(encoding="utf-8")
        document = Documents(
            uploaded_by_user_id=test_user.id,
            company_id=company.id,
            name=relative_path,
            content=content,
            source=f"evaluation:{relative_path}",
            file_type=".md",
            file_size=len(content.encode("utf-8")),
            sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            status="completed",
        )
        db_session.add(document)
        db_session.flush()
        document_ids[relative_path] = document.id
        for strategy in (PARAGRAPH_CHUNK_STRATEGY, SLIDING_WINDOW_CHUNK_STRATEGY):
            for chunk_index, chunk in enumerate(
                chunk_text_for_strategy(content, strategy)
            ):
                chunk_texts.append(chunk.content)
                chunk_metadata.append(
                    (
                        document.id,
                        strategy,
                        chunk_index,
                        chunk.content,
                        chunk.paragraph_start,
                        chunk.paragraph_end,
                    )
                )

    embedder = LocalEmbeddingProvider()
    embeddings = embedder.embed_batch(chunk_texts)
    assert len(embeddings) == len(chunk_metadata)
    for embedding, (document_id, strategy, chunk_index, content, start, end) in zip(
        embeddings, chunk_metadata
    ):
        chunk_rows.append(
            DocumentChunk(
                document_id=document_id,
                company_id=company.id,
                chunk_strategy=strategy,
                chunk_index=chunk_index,
                content=content,
                token_count=len(content.split()),
                embedding=embedding,
                paragraph_start=start,
                paragraph_end=end,
            )
        )
    db_session.add_all(chunk_rows)
    db_session.flush()

    reciprocal_ranks: list[float] = []
    hits = 0
    misses: list[str] = []
    top_k = int(os.getenv("FULL_CORPUS_TOP_K", "10"))
    split_metrics = {
        "dev": {"total": 0, "hits": 0, "rr": 0.0},
        "heldout": {"total": 0, "hits": 0, "rr": 0.0},
    }
    for relative_path, question in cases:
        split = _split(relative_path)
        split_metrics[split]["total"] += 1
        evidences = retrieve_evidence(
            db_session,
            question,
            company.id,
            embedder,
            top_k=top_k,
            min_score=-1.0,
        )
        rank = next(
            (
                index
                for index, evidence in enumerate(evidences, start=1)
                if evidence.document_id == document_ids[relative_path]
            ),
            None,
        )
        if rank is None:
            misses.append(relative_path)
            reciprocal_ranks.append(0.0)
        else:
            hits += 1
            reciprocal_ranks.append(1.0 / rank)
            split_metrics[split]["hits"] += 1
            split_metrics[split]["rr"] += 1.0 / rank

    recall_at_10 = hits / len(cases)
    mrr_at_10 = sum(reciprocal_ranks) / len(cases)
    print(
        "FULL_CORPUS_VECTOR_EVAL "
        f"cases={len(cases)} chunks={len(chunk_rows)} recall_at_{top_k}={recall_at_10:.4f} "
        f"mrr_at_{top_k}={mrr_at_10:.4f} misses={misses}"
    )
    for split, metric in split_metrics.items():
        assert metric["total"] >= 20
        print(
            "FULL_CORPUS_VECTOR_SPLIT "
            f"split={split} cases={metric['total']} "
            f"recall_at_{top_k}={metric['hits'] / metric['total']:.4f} "
            f"mrr_at_{top_k}={metric['rr'] / metric['total']:.4f}"
        )
    if os.getenv("RUN_FULL_CORPUS_RERANK_EVAL") == "1":
        settings = get_settings()
        reranker = LocalCrossEncoderReranker(settings.reranker_model)
        rerank_hits = 0
        rerank_reciprocal_ranks: list[float] = []
        sufficient = 0
        for relative_path, question in cases:
            candidates = retrieve_evidence(
                db_session,
                question,
                company.id,
                embedder,
                top_k=settings.rag_retrieval_top_k,
                min_score=-1.0,
            )
            reranked = rerank_evidences(
                question,
                candidates,
                reranker,
                top_k=settings.rag_rerank_top_k,
            )
            sufficient += int(
                check_sufficiency(
                    reranked,
                    question=question,
                    min_avg_score=settings.rag_rerank_min_score,
                )
            )
            rank = next(
                (
                    index
                    for index, evidence in enumerate(reranked, start=1)
                    if evidence.document_id == document_ids[relative_path]
                ),
                None,
            )
            if rank is None:
                rerank_reciprocal_ranks.append(0.0)
            else:
                rerank_hits += 1
                rerank_reciprocal_ranks.append(1.0 / rank)
        print(
            "FULL_CORPUS_RERANK_EVAL "
            f"recall_at_{settings.rag_rerank_top_k}={rerank_hits / len(cases):.4f} "
            f"mrr_at_{settings.rag_rerank_top_k}="
            f"{sum(rerank_reciprocal_ranks) / len(cases):.4f} "
            f"sufficient_rate={sufficient / len(cases):.4f}"
        )
    if os.getenv("RUN_B3B_RETRIEVAL_COMPARISON") == "1":
        settings = get_settings()
        comparison_cases = _development_cases(cases, limit=30)
        reranker = LocalCrossEncoderReranker(settings.reranker_model)
        for policy in _comparison_profiles():
            print(
                "B3B_RETRIEVAL_COMPARISON "
                + json.dumps(
                    _profile_metrics(
                        db_session=db_session,
                        cases=comparison_cases,
                        company_id=company.id,
                        document_ids=document_ids,
                        embedder=embedder,
                        policy=policy,
                        reranker=reranker,
                        top_k=top_k,
                        rerank_top_k=settings.rag_rerank_top_k,
                        min_rerank_score=settings.rag_rerank_min_score,
                    ),
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
    if os.getenv("REQUIRE_FULL_CORPUS_RAG_TARGET") == "1":
        # This is a release gate, deliberately separate from baseline collection.
        heldout = split_metrics["heldout"]
        assert heldout["hits"] / heldout["total"] >= 0.95
        assert heldout["rr"] / heldout["total"] >= 0.85


def test_frozen_east_contract_document_is_retrievable_for_its_gold_question(
    db_session, test_user
) -> None:
    """Reproduce only the paid smoke's document scope, without a provider model."""
    relative_path = "events/2025-08-east-sales-review.md"
    question = "有哪些资料支持CUST-0001暂停采购？"
    content = (CORPUS_ROOT / relative_path).read_text(encoding="utf-8")
    company = Company(name="frozen-east-contract-retrieval")
    db_session.add(company)
    db_session.flush()
    set_tenant_scope(db_session, company.id)
    document = Documents(
        uploaded_by_user_id=test_user.id,
        company_id=company.id,
        name=relative_path,
        content=content,
        source=f"evaluation:{relative_path}",
        file_type=".md",
        file_size=len(content.encode("utf-8")),
        sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        status="completed",
    )
    db_session.add(document)
    db_session.flush()
    chunks = chunk_text_for_strategy(content, PARAGRAPH_CHUNK_STRATEGY)
    embeddings = LocalEmbeddingProvider().embed_batch(
        [chunk.content for chunk in chunks]
    )
    assert len(embeddings) == len(chunks)
    db_session.add_all(
        [
            DocumentChunk(
                document_id=document.id,
                company_id=company.id,
                chunk_strategy=PARAGRAPH_CHUNK_STRATEGY,
                chunk_index=index,
                content=chunk.content,
                token_count=len(chunk.content.split()),
                embedding=embedding,
                paragraph_start=chunk.paragraph_start,
                paragraph_end=chunk.paragraph_end,
            )
            for index, (chunk, embedding) in enumerate(zip(chunks, embeddings))
        ]
    )
    db_session.flush()

    settings = get_settings()
    retrieval_query = RetrievalBrief(question=question).render_query()
    candidates = retrieve_evidence(
        db_session,
        retrieval_query,
        company.id,
        LocalEmbeddingProvider(),
        top_k=settings.rag_retrieval_top_k,
        min_score=settings.rag_retrieval_min_score,
        document_ids=[document.id],
        chunk_strategies=BASELINE_RETRIEVAL_POLICY.chunk_strategies,
    )
    reranked = rerank_evidences(
        retrieval_query,
        candidates,
        LocalCrossEncoderReranker(settings.reranker_model),
        top_k=settings.rag_rerank_top_k,
    )
    print(
        "FROZEN_EAST_CONTRACT_RETRIEVAL "
        f"candidates={len(candidates)} reranked={len(reranked)} "
        f"scores={[round(item.rerank_score or item.score, 4) for item in reranked]} "
        f"sufficient={check_sufficiency(reranked, question=retrieval_query, min_avg_score=settings.rag_rerank_min_score)}"
    )
    assert candidates
    assert reranked
    assert {item.document_id for item in reranked} == {document.id}
    assert any("合同" in item.content and "暂停" in item.content for item in reranked)
