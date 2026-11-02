"""Deterministic metrics for a fixed, permission-safe retrieval evaluation set."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievalEvaluationCase:
    case_id: str
    expected_chunk_ids: set[int]
    retrieved_chunk_ids: set[int]
    result_status: str
    citation_chunk_ids: set[int]
    expected_refusal: bool = False


@dataclass(frozen=True)
class RetrievalEvaluationMetrics:
    cases: int
    case_hit_rate: float
    chunk_recall: float
    chunk_precision: float
    citation_in_retrieval_rate: float
    refusal_accuracy: float


def evaluate_retrieval(
    cases: list[RetrievalEvaluationCase],
) -> RetrievalEvaluationMetrics:
    """Score retrieval output without inferring any business facts or quality claims."""
    if not cases:
        raise ValueError("at least one evaluation case is required")
    case_hits = 0
    expected_chunks = 0
    retrieved_chunks = 0
    matched_chunks = 0
    citation_total = 0
    citation_valid = 0
    refusal_correct = 0
    for case in cases:
        if (
            case.expected_chunk_ids
            and case.expected_chunk_ids & case.retrieved_chunk_ids
        ):
            case_hits += 1
        expected_chunks += len(case.expected_chunk_ids)
        retrieved_chunks += len(case.retrieved_chunk_ids)
        matched_chunks += len(case.expected_chunk_ids & case.retrieved_chunk_ids)
        citation_total += len(case.citation_chunk_ids)
        citation_valid += len(case.citation_chunk_ids & case.retrieved_chunk_ids)
        refused = case.result_status == "insufficient_evidence"
        refusal_correct += int(refused == case.expected_refusal)
    return RetrievalEvaluationMetrics(
        cases=len(cases),
        case_hit_rate=case_hits / len(cases),
        chunk_recall=(matched_chunks / expected_chunks if expected_chunks else 1.0),
        chunk_precision=(
            matched_chunks / retrieved_chunks if retrieved_chunks else 1.0
        ),
        citation_in_retrieval_rate=(
            citation_valid / citation_total if citation_total else 1.0
        ),
        refusal_accuracy=refusal_correct / len(cases),
    )


@dataclass(frozen=True)
class RankedRetrievalCase:
    """One question with document-level relevance and the ranked document ids returned."""

    case_id: str
    split: str
    relevant_document_ids: frozenset[int]
    ranked_document_ids: list[int]


def _dedupe(ids: list[int]) -> list[int]:
    # Several chunks of one document must not inflate its rank or recall.
    return list(dict.fromkeys(ids))


def _aggregate(cases: list[RankedRetrievalCase], ks: tuple[int, ...]) -> dict:
    totals: dict[str, float] = {f"hit_at_{k}": 0.0 for k in ks}
    totals.update({f"recall_at_{k}": 0.0 for k in ks})
    totals["mrr"] = 0.0
    for case in cases:
        ranked = _dedupe(case.ranked_document_ids)
        relevant = case.relevant_document_ids
        for k in ks:
            found = relevant.intersection(ranked[:k])
            totals[f"hit_at_{k}"] += 1.0 if found else 0.0
            totals[f"recall_at_{k}"] += len(found) / len(relevant)
        first = next(
            (rank for rank, doc in enumerate(ranked, start=1) if doc in relevant),
            None,
        )
        totals["mrr"] += 1.0 / first if first else 0.0
    count = len(cases)
    return {"cases": count, **{name: value / count for name, value in totals.items()}}


def evaluate_ranked_retrieval(
    cases: list[RankedRetrievalCase], *, ks: tuple[int, ...]
) -> dict:
    """Hit@k, Recall@k and MRR at document level, overall and per split."""
    if not cases or not ks:
        raise ValueError("ranked retrieval evaluation requires cases and k values")
    if any(not case.relevant_document_ids for case in cases):
        raise ValueError("every ranked retrieval case needs relevant documents")
    max_k = max(ks)
    splits = sorted({case.split for case in cases})
    return {
        "overall": _aggregate(cases, ks),
        "by_split": {
            split: _aggregate([c for c in cases if c.split == split], ks)
            for split in splits
        },
        "misses_at_max_k": [
            case.case_id
            for case in cases
            if not case.relevant_document_ids.intersection(
                _dedupe(case.ranked_document_ids)[:max_k]
            )
        ],
    }
