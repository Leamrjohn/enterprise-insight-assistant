from app.services.retrieval_evaluation import (
    RetrievalEvaluationCase,
    evaluate_retrieval,
)


def test_fixed_retrieval_evaluation_reports_metrics_without_claiming_model_quality() -> (
    None
):
    metrics = evaluate_retrieval(
        [
            RetrievalEvaluationCase(
                case_id="sales-decline-evidence",
                expected_chunk_ids={11},
                retrieved_chunk_ids={11, 12},
                citation_chunk_ids={11},
                result_status="ready",
            ),
            RetrievalEvaluationCase(
                case_id="insufficient-documents",
                expected_chunk_ids=set(),
                retrieved_chunk_ids=set(),
                citation_chunk_ids=set(),
                result_status="insufficient_evidence",
                expected_refusal=True,
            ),
            RetrievalEvaluationCase(
                case_id="wrong-citation",
                expected_chunk_ids={21},
                retrieved_chunk_ids={21},
                citation_chunk_ids={99},
                result_status="ready",
            ),
        ]
    )

    assert metrics.cases == 3
    assert metrics.recall_at_k == 2 / 3
    assert metrics.citation_valid_rate == 1 / 2
    assert metrics.refusal_accuracy == 1.0


def test_evaluation_requires_a_non_empty_fixed_case_set() -> None:
    try:
        evaluate_retrieval([])
    except ValueError as error:
        assert str(error) == "at least one evaluation case is required"
    else:
        raise AssertionError("empty evaluation set must be rejected")
