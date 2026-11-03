import pytest
from app.modules.evaluation.retrieval import (
    RankedRetrievalCase,
    evaluate_ranked_retrieval,
)


def test_ranked_metrics_count_documents_once_and_score_multi_document_scope() -> None:
    metrics = evaluate_ranked_retrieval(
        [
            # Duplicate chunks of document 7 count once; relevant docs at ranks 2 and 3.
            RankedRetrievalCase("a", "development", frozenset({1, 2}), [7, 7, 1, 2]),
            RankedRetrievalCase("b", "development", frozenset({5}), [5, 9]),
            RankedRetrievalCase("c", "heldout", frozenset({4}), [8, 9]),
        ],
        ks=(1, 3),
    )

    overall = metrics["overall"]
    assert overall["cases"] == 3
    assert overall["hit_at_1"] == pytest.approx(1 / 3)
    assert overall["hit_at_3"] == pytest.approx(2 / 3)
    # a: both scope docs in top 3 -> 1.0; b: 1.0; c: 0.0
    assert overall["recall_at_3"] == pytest.approx(2 / 3)
    # a: first relevant at document rank 2 -> 0.5; b: 1.0; c: 0
    assert overall["mrr"] == pytest.approx(0.5)
    assert metrics["by_split"]["heldout"]["hit_at_3"] == 0.0
    assert metrics["misses_at_max_k"] == ["c"]


def test_ranked_metrics_reject_empty_inputs() -> None:
    with pytest.raises(ValueError):
        evaluate_ranked_retrieval([], ks=(3,))
    with pytest.raises(ValueError):
        evaluate_ranked_retrieval(
            [RankedRetrievalCase("a", "development", frozenset(), [1])], ks=(3,)
        )


def test_fixture_questions_have_unique_scopes_inside_the_corpus() -> None:
    import json

    from scripts.evaluation.run_retrieval_evaluation import (
        CORPUS_ROOT,
        FIXTURE_ROOT,
        load_scoped_questions,
    )

    questions = load_scoped_questions(FIXTURE_ROOT)
    corpus = {
        artifact["path"]
        for artifact in json.loads(
            (CORPUS_ROOT / "manifest.json").read_text(encoding="utf-8")
        )["artifacts"]
    }

    assert questions
    assert len({(q["question"], tuple(q["scope"])) for q in questions}) == len(
        questions
    )
    assert all(set(q["scope"]) <= corpus for q in questions)


def test_older_evaluation_scripts_can_still_index_without_naming_strategies() -> None:
    import inspect

    from scripts.evaluation.run_retrieval_evaluation import _index_corpus

    default = inspect.signature(_index_corpus).parameters["strategies"].default

    assert default == ("paragraph_v1", "sliding_window_v1")


def test_compiled_volumes_keep_every_answer_and_map_each_original_file() -> None:
    from scripts.evaluation.run_retrieval_evaluation import compile_volumes

    sources = [(f"crm/{i}.md", f"# 记录{i}\n\n答案{i}") for i in range(9)]
    sources.append(("finance/a.md", "# 财务\n\n答案财务"))

    volumes, volume_of = compile_volumes(sources, documents_per_volume=8)

    assert [name for name, _ in volumes] == [
        "volume:crm-1",
        "volume:crm-2",
        "volume:finance-1",
    ]
    assert volume_of["crm/0.md"] == "volume:crm-1"
    assert volume_of["crm/8.md"] == "volume:crm-2"
    text = dict(volumes)
    assert all(f"答案{i}" in text[volume_of[f"crm/{i}.md"]] for i in range(9))
    assert "保密声明" in text["volume:finance-1"]
