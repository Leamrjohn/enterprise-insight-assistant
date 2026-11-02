"""Evaluate the sentence support check, on labelled sentences and on real answers.

sentences: labelled fixture sentences through the real check.
end_to_end: real retrieval, answer and check for the answer-labelled questions,
inside a rolled-back transaction.

record: real gateway behind BudgetGuardGateway, every response saved as a cassette.
replay: cassettes only; a missing recording fails instead of calling a model.

Run (evaluation container, agent_platform_test):
    python -m scripts.evaluation.run_support_evaluation --mode record \
        --cassette-dir /app/storage/cassettes/support_v1
"""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path

from app.core.gateway.base import ModelGateway
from app.core.gateway.replay import RecordReplayGateway
from app.core.settings import get_settings
from app.db.session import engine, set_tenant_scope
from app.main import app  # noqa: F401 - registers every model for the mapper
from app.modules.analysis.agent_protocol import AgentInput
from app.modules.analysis.tool_protocol import Tool, ToolInput, ToolOutput
from app.modules.evaluation.support_check import (
    summarize_end_to_end,
    summarize_support_cases,
)
from app.modules.identity.models import User
from app.modules.knowledge.agent import KnowledgeAgent
from app.modules.knowledge.rag.embeddings_local import LocalEmbeddingProvider
from app.modules.knowledge.rag.engine import build_prompt, check_sufficiency
from app.modules.knowledge.rag.policy import HYBRID_RETRIEVAL_POLICY
from app.modules.knowledge.rag.reranker import (
    LocalCrossEncoderReranker,
    rerank_evidences,
)
from app.modules.knowledge.rag.retrieval import retrieve_evidence
from app.modules.knowledge.rag.support import check_support
from app.modules.knowledge.rag.validity import ValidityWindow, business_today
from app.modules.organizations.models import Company
from scripts.evaluation.run_planner_route_evaluation import (
    BudgetGuardExceeded,
    BudgetGuardGateway,
)
from scripts.evaluation.run_retrieval_evaluation import (
    TRAP_FIXTURE,
    _index_corpus,
    _index_keywords,
    load_gold_questions,
)
from sqlalchemy.orm import Session

FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "evaluation_support"
    / "support_cases_v1.json"
)
EXPECTED_DATABASE = "agent_platform_test"


def evaluate_sentences(gateway: ModelGateway, cases: list[dict]) -> list[dict]:
    today = business_today()
    rows = []
    for case in cases:
        outcome = check_support(
            gateway,
            question=case["question"],
            answer=case["sentence"],
            evidences=[
                {
                    "chunk_id": 1,
                    "document_id": 1,
                    "content": case["evidence"],
                    "score": 1.0,
                }
            ],
            window=ValidityWindow(today, today),
        )
        rows.append(
            {
                "case_id": case["case_id"],
                "split": case["split"],
                "kind": case["kind"],
                "expected": case["expected"],
                "verdict": outcome.sentences[0].verdict,
                "kept": outcome.sentences[0].kept,
            }
        )
    return rows


class _InTransactionRag(Tool):
    """The RAG tool's steps on this script's rolled-back session.

    The real tool opens its own connection, which cannot see uncommitted rows.
    """

    def __init__(self, db: Session, company_id: int, reranker, settings) -> None:
        self._db = db
        self._company_id = company_id
        self._reranker = reranker
        self._settings = settings
        self._embedder = LocalEmbeddingProvider()

    @property
    def name(self) -> str:
        return "rag_search"

    @property
    def description(self) -> str:
        return "retrieval inside the evaluation transaction"

    def execute(self, input: ToolInput) -> ToolOutput:
        question = input.parameters["question"]
        policy = HYBRID_RETRIEVAL_POLICY
        evidences = retrieve_evidence(
            self._db,
            question,
            self._company_id,
            self._embedder,
            top_k=self._settings.rag_retrieval_top_k,
            min_score=self._settings.rag_retrieval_min_score,
            chunk_strategies=policy.chunk_strategies,
            validity=ValidityWindow.from_parameter(input.parameters["validity_window"]),
            keyword_tokenizer=policy.keyword_tokenizer,
        )
        evidences = rerank_evidences(
            question, evidences, self._reranker, top_k=self._settings.rag_rerank_top_k
        )
        if not check_sufficiency(
            evidences,
            question=question,
            min_avg_score=self._settings.rag_rerank_min_score,
        ):
            return ToolOutput(
                success=True,
                data={
                    "status": "insufficient_evidence",
                    "answer": "无法回答：资料不足",
                    "evidences": [],
                },
            )
        system_prompt, user_prompt, allowed = build_prompt(question, evidences)
        return ToolOutput(
            success=True,
            data={
                "status": "ready",
                "evidences": [
                    {
                        "chunk_id": e.chunk_id,
                        "document_id": e.document_id,
                        "content": e.content,
                        "score": e.score,
                        "rerank_score": e.rerank_score,
                        "effective_from": e.effective_from,
                        "effective_to": e.effective_to,
                        "applies_to": e.applies_to,
                    }
                    for e in evidences
                ],
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "allowed_chunk_ids": sorted(allowed),
            },
        )


class _CapturingGateway(ModelGateway):
    """Remembers replies so the answer before the check can be compared."""

    def __init__(self, inner: ModelGateway) -> None:
        self._inner = inner
        self.replies: list[str] = []

    def chat(self, prompt, system_prompt=None, *, json_mode=False):
        reply = self._inner.chat(prompt, system_prompt, json_mode=json_mode)
        self.replies.append(reply)
        return reply

    def count_tokens(self, text: str) -> int:
        return self._inner.count_tokens(text)


def _case_row(case_id, answer, output, replies, stale_id=None) -> dict:
    try:
        before = json.loads(replies[0])["answer"] if replies else ""
    except (ValueError, KeyError, TypeError):
        before = ""
    try:
        verdicts = json.loads(replies[1])["verdicts"] if len(replies) > 1 else []
    except (ValueError, KeyError, TypeError):
        verdicts = []
    removed = sum(
        v.get("verdict") in {"unsupported", "not_applicable"} for v in verdicts
    )
    return {
        "case_id": case_id,
        "answer_before_check": answer in before,
        "answer_after_check": answer in (output.answer or ""),
        "answer_in_cited_chunk": any(answer in e["content"] for e in output.evidence),
        "stale_cited": sum(e["document_id"] == stale_id for e in output.evidence),
        "cited": bool(output.evidence),
        "sentences": len(verdicts),
        "sentences_removed": removed,
        "error_code": output.error_code,
    }


def evaluate_end_to_end(gateway: ModelGateway) -> list[dict]:
    settings = get_settings()
    traps = json.loads(TRAP_FIXTURE.read_text(encoding="utf-8"))
    connection = engine.connect()
    transaction = connection.begin()
    db = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        user = User(name="support-evaluation", api_key="support-evaluation-key")
        company = Company(name="support-evaluation")
        db.add_all([user, company])
        db.flush()
        set_tenant_scope(db, company.id)
        document_ids = _index_corpus(
            db,
            company_id=company.id,
            user_id=user.id,
            trap_documents=traps["documents"],
        )
        _index_keywords(db, company.id, "jieba")
        tool = _InTransactionRag(
            db,
            company.id,
            LocalCrossEncoderReranker(settings.reranker_model),
            settings,
        )
        capture = _CapturingGateway(gateway)
        agent = KnowledgeAgent(rag_tool=tool, gateway=capture, support_check=True)
        rows = []
        cases = [
            (q["case_id"], q["question"], q["answer"], None)
            for q in load_gold_questions()
        ] + [
            (
                c["case_id"],
                c["question"],
                c["answer"],
                document_ids[f"trap:{c['stale']}"],
            )
            for c in traps["cases"]
        ]
        for case_id, question, answer, stale_id in cases:
            capture.replies = []
            output = agent.run(
                AgentInput(
                    question=question,
                    user_id=user.id,
                    context={"company_id": company.id},
                )
            )
            rows.append(_case_row(case_id, answer, output, capture.replies, stale_id))
            print(f"{case_id}: {output.error_code}", file=sys.stderr, flush=True)
        return rows
    finally:
        db.close()
        transaction.rollback()
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mode", choices=("record", "replay"), required=True)
    parser.add_argument("--cassette-dir", type=Path, required=True)
    parser.add_argument("--max-calls", type=int, default=150)
    parser.add_argument("--max-cost", type=Decimal, default=Decimal("0.12"))
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if engine.url.database != EXPECTED_DATABASE:
        sys.exit(f"refusing to run outside {EXPECTED_DATABASE}")

    guard: BudgetGuardGateway | None = None
    if args.mode == "replay":
        gateway: ModelGateway = RecordReplayGateway(args.cassette_dir, mode="replay")
    else:
        from app.core.gateway.factory import get_model_gateway

        guard = BudgetGuardGateway(
            get_model_gateway(), max_calls=args.max_calls, max_cost=args.max_cost
        )
        gateway = RecordReplayGateway(args.cassette_dir, mode="record", inner=guard)

    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    stopped, sentences, end_to_end = None, [], []
    try:
        sentences = evaluate_sentences(gateway, fixture["cases"])
        end_to_end = evaluate_end_to_end(gateway)
    except BudgetGuardExceeded as exc:
        stopped = str(exc)
    report = {
        "mode": args.mode,
        "stopped_by_budget_guard": stopped,
        "model_calls": guard.calls if guard else 0,
        "estimated_cost_usd": str(guard.estimated_cost) if guard else "0",
        "sentences": summarize_support_cases(sentences) if sentences else None,
        "end_to_end": summarize_end_to_end(end_to_end) if end_to_end else None,
    }
    if args.report:
        args.report.write_text(
            json.dumps(
                {**report, "sentence_rows": sentences, "end_to_end_rows": end_to_end},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
