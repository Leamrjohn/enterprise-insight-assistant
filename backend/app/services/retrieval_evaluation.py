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
    recall_at_k: float
    citation_valid_rate: float
    refusal_accuracy: float


def evaluate_retrieval(
    cases: list[RetrievalEvaluationCase],
) -> RetrievalEvaluationMetrics:
    """Score retrieval output without inferring any business facts or quality claims."""
    if not cases:
        raise ValueError("at least one evaluation case is required")
    recall_hits = 0
    citation_total = 0
    citation_valid = 0
    refusal_correct = 0
    for case in cases:
        if (
            case.expected_chunk_ids
            and case.expected_chunk_ids & case.retrieved_chunk_ids
        ):
            recall_hits += 1
        citation_total += len(case.citation_chunk_ids)
        citation_valid += len(case.citation_chunk_ids & case.retrieved_chunk_ids)
        refused = case.result_status == "insufficient_evidence"
        refusal_correct += int(refused == case.expected_refusal)
    return RetrievalEvaluationMetrics(
        cases=len(cases),
        recall_at_k=recall_hits / len(cases),
        citation_valid_rate=(
            citation_valid / citation_total if citation_total else 1.0
        ),
        refusal_accuracy=refusal_correct / len(cases),
    )
