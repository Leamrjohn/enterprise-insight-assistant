"""Rerank scores behind the sufficiency gate, per question.  No model is called.

Shows what each gate rule would decide for answerable and unanswerable questions.

Run (evaluation container, agent_platform_test):
    python -m scripts.evaluation.diagnose_sufficiency_gate
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from app.core.settings import get_settings
from app.db.session import engine, set_tenant_scope
from app.main import app  # noqa: F401 - registers every model for the mapper
from app.modules.identity.models import User
from app.modules.knowledge.rag.embeddings_local import LocalEmbeddingProvider
from app.modules.knowledge.rag.policy import HYBRID_RETRIEVAL_POLICY
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
from scripts.evaluation.run_retrieval_evaluation import (
    TRAP_FIXTURE,
    _index_corpus,
    _index_keywords,
    load_gold_questions,
)
from sqlalchemy.orm import Session

UNANSWERABLE = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "evaluation_support"
    / "unanswerable_v1.json"
)


def main() -> None:
    if engine.url.database != "agent_platform_test":
        sys.exit("refusing to run outside agent_platform_test")
    settings = get_settings()
    traps = json.loads(TRAP_FIXTURE.read_text(encoding="utf-8"))
    cases = [
        ("answerable", q["case_id"], q["question"], q["answer"])
        for q in load_gold_questions()
    ]
    cases += [
        ("answerable", c["case_id"], c["question"], c["answer"]) for c in traps["cases"]
    ]
    cases += [
        ("unanswerable", c["case_id"], c["question"], None)
        for c in json.loads(UNANSWERABLE.read_text(encoding="utf-8"))["cases"]
    ]
    connection = engine.connect()
    transaction = connection.begin()
    db = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        user = User(name="gate-diagnosis", api_key="gate-diagnosis-key")
        company = Company(name="gate-diagnosis")
        db.add_all([user, company])
        db.flush()
        set_tenant_scope(db, company.id)
        _index_corpus(
            db,
            company_id=company.id,
            user_id=user.id,
            trap_documents=traps["documents"],
        )
        _index_keywords(db, company.id, "jieba")
        embedder = LocalEmbeddingProvider()
        reranker = LocalCrossEncoderReranker(settings.reranker_model)
        rows = []
        for group, case_id, question, answer in cases:
            evidences = rerank_evidences(
                question,
                retrieve_evidence(
                    db,
                    question,
                    company.id,
                    embedder,
                    top_k=settings.rag_retrieval_top_k,
                    min_score=settings.rag_retrieval_min_score,
                    chunk_strategies=HYBRID_RETRIEVAL_POLICY.chunk_strategies,
                    validity=resolve_validity_window(question, business_today()),
                    keyword_tokenizer=HYBRID_RETRIEVAL_POLICY.keyword_tokenizer,
                ),
                reranker,
                top_k=settings.rag_rerank_top_k,
            )
            rows.append(
                {
                    "group": group,
                    "case_id": case_id,
                    "scores": [round(e.rerank_score, 3) for e in evidences],
                    "answer_retrieved": answer is not None
                    and any(answer in e.content for e in evidences),
                }
            )
    finally:
        db.close()
        transaction.rollback()
        connection.close()
    print(json.dumps(rows, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
