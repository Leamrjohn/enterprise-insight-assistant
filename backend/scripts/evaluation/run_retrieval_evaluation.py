"""Offline document-level retrieval evaluation over the full knowledge corpus.

Indexes every corpus artifact into the isolated test database inside one
transaction, scores the fixture questions that declare a document scope, and
rolls everything back.  Only local embedding and reranking models are used.

Run (evaluation container, agent_platform_test):
    python scripts/evaluation/run_retrieval_evaluation.py > result.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date
from pathlib import Path
from statistics import fmean
from time import perf_counter

from app.core.settings import get_settings
from app.db.session import engine, set_tenant_scope
from app.modules.documents.chunks import DocumentChunk
from app.modules.documents.models import Documents
from app.modules.documents.search_tokens import search_vector_expression
from app.modules.documents.versioning import register_document_version
from app.modules.evaluation.retrieval import (
    RankedRetrievalCase,
    answer_hit_rates,
    evaluate_ranked_retrieval,
    score_version_traps,
)
from app.modules.identity.models import User
from app.modules.knowledge.rag.embeddings_local import (
    LOCAL_EMBEDDING_MODEL_NAME,
    LocalEmbeddingProvider,
)
from app.modules.knowledge.rag.engine import build_prompt, keep_relevant
from app.modules.knowledge.rag.policy import (
    BASELINE_RETRIEVAL_POLICY,
    DUAL_CHUNK_RETRIEVAL_POLICY,
    HYBRID_RETRIEVAL_POLICY,
    PASSAGE_RETRIEVAL_POLICY,
    RetrievalPolicy,
)
from app.modules.knowledge.rag.reranker import (
    LocalCrossEncoderReranker,
    rerank_evidences,
)
from app.modules.knowledge.rag.retrieval import retrieve_evidence
from app.modules.knowledge.rag.validity import (
    business_today,
    resolve_validity_window,
)
from app.modules.organizations.models import Company
from app.utils.document_chunk import (
    PARAGRAPH_CHUNK_STRATEGY,
    SLIDING_WINDOW_CHUNK_STRATEGY,
    chunk_text_for_strategy,
)
from sqlalchemy import select, update
from sqlalchemy.orm import Session

BACKEND_ROOT = Path(__file__).resolve().parents[2]
CORPUS_ROOT = BACKEND_ROOT.parent / "data" / "business_knowledge_base"
FIXTURE_ROOT = BACKEND_ROOT / "tests" / "fixtures" / "evaluation"
RETRIEVAL_FIXTURES = BACKEND_ROOT / "tests" / "fixtures" / "evaluation_retrieval"
GOLD_FIXTURE = RETRIEVAL_FIXTURES / "retrieval_gold_v2.json"
TRAP_FIXTURE = RETRIEVAL_FIXTURES / "version_traps_v1.json"
EXPECTED_DATABASE = "agent_platform_test"
CANDIDATE_K = 10

POLICIES = (
    BASELINE_RETRIEVAL_POLICY,
    RetrievalPolicy(
        policy_id="paragraph_vector_no_rerank_v1",
        chunk_strategies=(PARAGRAPH_CHUNK_STRATEGY,),
        rerank_enabled=False,
    ),
    DUAL_CHUNK_RETRIEVAL_POLICY,
    RetrievalPolicy(
        policy_id="paragraph_jieba_rrf_no_rerank_v1",
        chunk_strategies=(PARAGRAPH_CHUNK_STRATEGY,),
        rerank_enabled=False,
        keyword_tokenizer="jieba",
    ),
    RetrievalPolicy(
        policy_id="paragraph_bigram_rrf_no_rerank_v1",
        chunk_strategies=(PARAGRAPH_CHUNK_STRATEGY,),
        rerank_enabled=False,
        keyword_tokenizer="bigram",
    ),
    RetrievalPolicy(
        policy_id="paragraph_bigram_rrf_rerank_v1",
        chunk_strategies=(PARAGRAPH_CHUNK_STRATEGY,),
        rerank_enabled=True,
        keyword_tokenizer="bigram",
    ),
    HYBRID_RETRIEVAL_POLICY,
    PASSAGE_RETRIEVAL_POLICY,
)

VOLUME_DOCUMENTS = 8
VOLUME_FRONT_MATTER = """## 修订记录
本文件由公司文件管理部门统一维护，修订时须经部门负责人审批，并在发布后通知相关人员。

## 保密声明
本文件内容仅供公司内部使用，未经书面许可不得复制、转发或向第三方披露，违者依公司制度处理。

## 使用须知
使用人应确认所持版本为最新有效版本，打印件仅作参考，归档、借阅和销毁均按档案管理规定办理。"""


def compile_volumes(
    sources: list[tuple[str, str]], *, documents_per_volume: int = VOLUME_DOCUMENTS
) -> tuple[list[tuple[str, str]], dict[str, str]]:
    """Bind short documents into long ones, the shape real company files tend to have.

    Each folder becomes numbered volumes with shared front matter.  No wording is
    changed, so the answers the existing questions expect are still in the text.
    """
    folders: dict[str, list[tuple[str, str]]] = {}
    for path, content in sorted(sources):
        folders.setdefault(path.split("/", 1)[0], []).append((path, content))
    volumes: list[tuple[str, str]] = []
    volume_of: dict[str, str] = {}
    for folder, documents in folders.items():
        for index in range(0, len(documents), documents_per_volume):
            bound = documents[index : index + documents_per_volume]
            number = index // documents_per_volume + 1
            name = f"volume:{folder}-{number}"
            cover = f"# {folder} 资料汇编 第{number}册\n\n{VOLUME_FRONT_MATTER}"
            body = "\n\n".join(content for _, content in bound)
            volumes.append((name, f"{cover}\n\n{body}"))
            volume_of.update({path: name for path, _ in bound})
    return volumes, volume_of


def load_scoped_questions(fixture_root: Path) -> list[dict]:
    """Unique (question, document scope) pairs from analysis fixtures."""
    seen: dict[tuple[str, tuple[str, ...]], dict] = {}
    for path in sorted(fixture_root.glob("*.json")):
        for case in json.loads(path.read_text(encoding="utf-8")).get("cases", []):
            scope = tuple(sorted(case.get("document_scope") or []))
            if not scope or case.get("evaluation_kind", "analysis") != "analysis":
                continue
            key = (case["question"], scope)
            # Keep the first case id; a held-out label wins so it is never trained on.
            if key not in seen or case["split"] == "heldout":
                seen[key] = {
                    "case_id": case["case_id"],
                    "split": case["split"],
                    "question": case["question"],
                    "scope": list(scope),
                }
    return list(seen.values())


def load_gold_questions(path: Path = GOLD_FIXTURE) -> list[dict]:
    """Hand-labelled questions whose answer text must appear in a retrieved chunk."""
    return [
        {
            "case_id": case["case_id"],
            "split": case["split"],
            "question": case["question"],
            "scope": case["relevant"],
            "answer": case["answer"],
        }
        for case in json.loads(path.read_text(encoding="utf-8"))["cases"]
    ]


def _index_corpus(
    db: Session,
    *,
    company_id: int,
    user_id: int,
    trap_documents: list[dict],
    strategies: tuple[str, ...] = (
        PARAGRAPH_CHUNK_STRATEGY,
        SLIDING_WINDOW_CHUNK_STRATEGY,
    ),
    register_versions: bool = True,
    compiled: bool = False,
) -> dict[str, int]:
    manifest = json.loads((CORPUS_ROOT / "manifest.json").read_text(encoding="utf-8"))
    sources = [
        (
            artifact["path"],
            (CORPUS_ROOT / artifact["path"]).read_text(encoding="utf-8"),
        )
        for artifact in manifest["artifacts"]
    ]
    volume_of: dict[str, str] = {}
    if compiled:
        sources, volume_of = compile_volumes(sources)
    # Trap documents exist only in this rolled-back transaction.
    sources += [(f"trap:{doc['key']}", doc["content"]) for doc in trap_documents]
    trap_by_path = {f"trap:{doc['key']}": doc for doc in trap_documents}
    document_ids: dict[str, int] = {}
    texts: list[str] = []
    metadata: list[tuple[int, str, int, str, int, int]] = []
    for relative_path, content in sources:
        document = Documents(
            uploaded_by_user_id=user_id,
            company_id=company_id,
            name=relative_path,
            content=content,
            source=f"evaluation:{relative_path}",
            file_type=".md",
            file_size=len(content.encode("utf-8")),
            sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            status="completed",
        )
        db.add(document)
        db.flush()
        document_ids[relative_path] = document.id
        if register_versions and relative_path in trap_by_path:
            trap = trap_by_path[relative_path]
            register_document_version(
                db,
                document=document,
                version_group=trap["group"],
                version_number=trap["version"],
                effective_from=date.fromisoformat(trap["effective_from"]),
            )
        for strategy in strategies:
            for index, chunk in enumerate(chunk_text_for_strategy(content, strategy)):
                texts.append(chunk.content)
                metadata.append(
                    (
                        document.id,
                        strategy,
                        index,
                        chunk.content,
                        chunk.paragraph_start,
                        chunk.paragraph_end,
                    )
                )
    embeddings = LocalEmbeddingProvider().embed_batch(texts)
    db.add_all(
        DocumentChunk(
            document_id=document_id,
            company_id=company_id,
            chunk_strategy=strategy,
            chunk_index=index,
            content=content,
            token_count=len(content.split()),
            embedding=embedding,
            paragraph_start=start,
            paragraph_end=end,
        )
        for embedding, (document_id, strategy, index, content, start, end) in zip(
            embeddings, metadata, strict=True
        )
    )
    db.flush()
    # Questions name the original files; each now lives inside a volume.
    document_ids.update(
        {path: document_ids[volume] for path, volume in volume_of.items()}
    )
    return document_ids


def _index_keywords(db: Session, company_id: int, tokenizer: str) -> None:
    """Rebuild the keyword index with this policy's tokenizer."""
    chunks = db.execute(
        select(DocumentChunk.id, DocumentChunk.content).where(
            DocumentChunk.company_id == company_id
        )
    ).all()
    for chunk_id, content in chunks:
        db.execute(
            update(DocumentChunk)
            .where(DocumentChunk.id == chunk_id)
            .values(search_vector=search_vector_expression(content, tokenizer))
        )
    db.flush()


def _evaluate_policy(
    db: Session,
    *,
    policy: RetrievalPolicy,
    questions: list[dict],
    trap_cases: list[dict],
    company_id: int,
    document_ids: dict[str, int],
    embedder: LocalEmbeddingProvider,
    reranker: LocalCrossEncoderReranker,
    final_k: int,
    candidate_k: int,
    min_rerank_score: float,
) -> dict:
    started = perf_counter()
    print(f"evaluating {policy.policy_id}", file=sys.stderr, flush=True)
    if policy.keyword_tokenizer:
        _index_keywords(db, company_id, policy.keyword_tokenizer)
    candidates: list[RankedRetrievalCase] = []
    finals: list[RankedRetrievalCase] = []
    answers: list[dict] = []
    prompt_answers: list[dict] = []
    prompt_chars: list[int] = []

    def in_prompt(question: str, final: list) -> list:
        """What the model would really read: the steps RAGTool runs after reranking."""
        kept = (
            keep_relevant(final, min_rerank_score) if policy.rerank_enabled else final
        )
        if not kept:
            return []
        _, _, allowed = build_prompt(question, kept)
        return [evidence for evidence in kept if evidence.chunk_id in allowed]

    def retrieve_final(question: str):
        evidences = retrieve_evidence(
            db,
            question,
            company_id,
            embedder,
            top_k=candidate_k,
            min_score=-1.0,
            chunk_strategies=policy.chunk_strategies,
            # The same code path as production, not the fixture's label.
            validity=resolve_validity_window(question, business_today()),
            keyword_tokenizer=policy.keyword_tokenizer,
        )
        if policy.rerank_enabled:
            final = rerank_evidences(question, evidences, reranker, top_k=final_k)
        else:
            final = evidences[:final_k]
        return evidences, final

    for item in questions:
        relevant = frozenset(document_ids[path] for path in item["scope"])
        evidences, final = retrieve_final(item["question"])
        candidates.append(
            RankedRetrievalCase(
                item["case_id"],
                item["split"],
                relevant,
                [e.document_id for e in evidences],
            )
        )
        finals.append(
            RankedRetrievalCase(
                item["case_id"],
                item["split"],
                relevant,
                [e.document_id for e in final],
            )
        )
        if "answer" in item:
            answers.append(
                {
                    "case_id": item["case_id"],
                    "split": item["split"],
                    "found": any(item["answer"] in e.content for e in final),
                }
            )
            sent = in_prompt(item["question"], final)
            prompt_chars.append(sum(len(e.content) for e in sent))
            prompt_answers.append(
                {
                    "case_id": item["case_id"],
                    "split": item["split"],
                    "found": any(item["answer"] in e.content for e in sent),
                }
            )
    trap_rows = []
    for case in trap_cases:
        _, final = retrieve_final(case["question"])
        trap_rows.append(
            {
                "case_id": case["case_id"],
                "kind": case["kind"],
                "ranked": [e.document_id for e in final],
                "fresh": document_ids[f"trap:{case['fresh']}"],
                "stale": document_ids[f"trap:{case['stale']}"],
                "answer_found": any(case["answer"] in e.content for e in final),
            }
        )
    original_ids = {q["case_id"] for q in questions if "answer" not in q}
    return {
        "policy_id": policy.policy_id,
        "candidates": evaluate_ranked_retrieval(candidates, ks=(1, 3, 5, candidate_k)),
        "final": evaluate_ranked_retrieval(finals, ks=(1, final_k)),
        # The original 19 questions, comparable with the earlier baseline.
        "final_original_questions": evaluate_ranked_retrieval(
            [case for case in finals if case.case_id in original_ids], ks=(1, final_k)
        ),
        "answer_found": answer_hit_rates(answers),
        "answer_in_prompt": answer_hit_rates(prompt_answers),
        "prompt_chars": {"mean": round(fmean(prompt_chars)), "max": max(prompt_chars)},
        "version_traps": score_version_traps(trap_rows),
        "duration_ms": round((perf_counter() - started) * 1000),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--policies",
        nargs="*",
        help="policy ids to run; default all",
    )
    parser.add_argument(
        "--compiled",
        action="store_true",
        help="bind the corpus into long volumes before indexing",
    )
    parser.add_argument("--candidate-k", type=int, default=CANDIDATE_K)
    args = parser.parse_args()
    selected = [
        policy
        for policy in POLICIES
        if not args.policies or policy.policy_id in args.policies
    ]
    if engine.url.database != EXPECTED_DATABASE:
        sys.exit(f"refusing to run outside {EXPECTED_DATABASE}")
    settings = get_settings()
    questions = [*load_scoped_questions(FIXTURE_ROOT), *load_gold_questions()]
    traps = json.loads(TRAP_FIXTURE.read_text(encoding="utf-8"))
    connection = engine.connect()
    transaction = connection.begin()
    db = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        user = User(name="retrieval-evaluation", api_key="retrieval-evaluation-key")
        company = Company(name="retrieval-evaluation")
        db.add_all([user, company])
        db.flush()
        set_tenant_scope(db, company.id)
        indexing_started = perf_counter()
        document_ids = _index_corpus(
            db,
            company_id=company.id,
            user_id=user.id,
            trap_documents=traps["documents"],
            strategies=tuple(
                dict.fromkeys(
                    strategy
                    for policy in selected
                    for strategy in policy.chunk_strategies
                )
            ),
            compiled=args.compiled,
        )
        indexing_ms = round((perf_counter() - indexing_started) * 1000)
        print(
            f"indexed {len(document_ids)} documents in {indexing_ms} ms",
            file=sys.stderr,
        )
        embedder = LocalEmbeddingProvider()
        reranker = LocalCrossEncoderReranker(settings.reranker_model)
        result = {
            "corpus_shape": "compiled_volumes" if args.compiled else "original",
            "corpus_documents": len(set(document_ids.values())),
            "questions": len(questions),
            "splits": {
                split: sum(q["split"] == split for q in questions)
                for split in sorted({q["split"] for q in questions})
            },
            "embedding_model": LOCAL_EMBEDDING_MODEL_NAME,
            "reranker_model": settings.reranker_model,
            "candidate_k": args.candidate_k,
            "final_k": settings.rag_rerank_top_k,
            "indexing_ms": indexing_ms,
            "policies": [
                _evaluate_policy(
                    db,
                    policy=policy,
                    questions=questions,
                    trap_cases=traps["cases"],
                    company_id=company.id,
                    document_ids=document_ids,
                    embedder=embedder,
                    reranker=reranker,
                    final_k=settings.rag_rerank_top_k,
                    candidate_k=args.candidate_k,
                    min_rerank_score=settings.rag_rerank_min_score,
                )
                for policy in selected
            ],
        }
    finally:
        db.close()
        transaction.rollback()
        connection.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
