"""C7: a chunk past the cap keeps the sentences about the question, verbatim."""

import random

import pytest
from app.modules.knowledge.rag.engine import EvidenceRef, build_prompt, fit_evidences
from app.modules.runtime.context.compressors import (
    ELISION,
    excerpt,
    sentence_score,
    split_sentences,
)

QUESTION = "根据应收风险提示，对华北汽车零部件客户067建议按什么比例计提坏账准备？"
FILLER = "本季度库存周转保持平稳，物流时效略有改善。"  # no word of QUESTION
ANSWER = "华北汽车零部件客户067逾期超过180天，建议按35%计提坏账准备。"
LIMIT = "上述比例只适用于华北地区。"


def long_chunk(answer_at: int, tail: str = "") -> str:
    """Filler with ANSWER starting at character ``answer_at``, then ``tail``."""
    before = FILLER * (answer_at // len(FILLER) + 1)
    return before[:answer_at] + ANSWER + FILLER * 20 + tail


@pytest.mark.parametrize(
    "sentence, expected",
    [
        ("华东区8月销售额为1200万元。", 3),  # two words, then the number
        ("华东区天气晴朗。", 1),
        ("本月共有3天下雨。", 0),  # a number alone says nothing
        ("CUST-0001合同到期后暂停采购。", 4),  # the code holds a number too
        ("cust-0001 的华东订单有12笔。", 5),  # case is ignored
        ("", 0),
    ],
)
def test_a_sentence_scores_for_the_question_it_speaks_to(sentence, expected):
    terms, entities = {"华东", "销售额"}, {"cust-0001"}
    assert sentence_score(sentence, terms=terms, entities=entities) == expected


def test_sentences_join_back_to_the_text():
    text = "第一句。第二句！\n第三行\n\n结尾没有标点"
    assert "".join(split_sentences(text)) == text


def test_the_answer_at_character_900_survives():
    text = long_chunk(900)
    result = excerpt(text, QUESTION, 300)

    assert result is not None and ANSWER in result
    assert result.startswith(ELISION) and len(result) <= 300


def test_a_limit_at_the_end_survives():
    text = long_chunk(900, tail=LIMIT)
    result = excerpt(text, QUESTION, 300)

    assert result is not None
    assert ANSWER in result and result.endswith(LIMIT)


def test_nothing_about_the_question_gives_none():
    assert excerpt(FILLER * 50, QUESTION, 300) is None


def test_every_kept_piece_is_verbatim_and_fits():
    """Property test with a fixed seed: random sentences, numbers and codes."""
    rng = random.Random(7)
    words = [
        "华北",
        "客户",
        "比例",
        "库存",
        "物流",
        "CUST-0067",
        "35.5%",
        "180天",
        "，",
    ]
    ends = ["。", "！", "？", "；", "\n", ""]
    for _ in range(300):
        text = "".join(
            "".join(rng.choices(words, k=rng.randint(1, 6))) + rng.choice(ends)
            for _ in range(rng.randint(1, 30))
        )
        budget = rng.randint(1, 200)
        result = excerpt(text, "华北客户CUST-0067的比例是多少？", budget)
        if result is None:
            continue
        assert len(result) <= budget
        assert all(piece in text for piece in result.split(ELISION) if piece)


def evidence(chunk_id: int, content: str, score: float) -> EvidenceRef:
    return EvidenceRef(
        chunk_id=chunk_id, document_id=1, content=content, rerank_score=score
    )


def test_a_chunk_past_the_cap_is_excerpted_not_dropped():
    first = evidence(1, FILLER * 120, 0.9)  # 2520 characters
    second = evidence(2, long_chunk(900, tail=LIMIT), 0.8)

    _, prompt, allowed = build_prompt(QUESTION, [first, second])

    assert allowed == {1, 2}
    assert ANSWER in prompt and LIMIT in prompt  # 35% and 180天 unchanged
    fitted = fit_evidences(QUESTION, [first, second])
    assert sum(len(e.content) for e in fitted) <= 3000
    assert fit_evidences(QUESTION, fitted) == fitted


def test_chunks_that_fit_are_sent_as_before():
    chunks = [evidence(1, "销售额下降了15%", 0.9), evidence(2, "原因是成本上升", 0.8)]
    assert fit_evidences("为什么销售额下降", chunks) == chunks


def test_too_little_room_ends_the_list():
    first = evidence(1, FILLER * 142, 0.9)  # 2982 characters: 18 left
    second = evidence(2, ANSWER, 0.8)
    assert [e.chunk_id for e in fit_evidences(QUESTION, [first, second])] == [1]
