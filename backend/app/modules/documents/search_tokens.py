"""Turn Chinese text into the words PostgreSQL full-text search will index."""

import logging
import re
from collections.abc import Callable

import jieba
from sqlalchemy import func

jieba.setLogLevel(logging.WARNING)

_WORD = re.compile(r"[一-鿿a-z0-9]+")
_SINGLE_CHINESE = re.compile(r"[一-鿿]")
# Question words that match almost any chunk and say nothing about the topic.
_STOP_WORDS = frozenset(
    {
        "什么",
        "多少",
        "哪些",
        "哪个",
        "怎么",
        "怎样",
        "如何",
        "为什么",
        "是否",
        "可以",
        "需要",
        "我们",
        "请问",
        "现在",
        "目前",
        "当前",
        "以及",
        "或者",
        "因为",
        "所以",
    }
)


def jieba_tokens(text: str) -> list[str]:
    """Words for the search index; a long word also yields its parts."""
    return [
        token
        for token in jieba.cut_for_search(text.lower())
        if _WORD.fullmatch(token)
        and not _SINGLE_CHINESE.fullmatch(token)
        and token not in _STOP_WORDS
    ]


def bigram_tokens(text: str) -> list[str]:
    """Overlapping two-character pieces; the comparison baseline for jieba."""
    pieces = _WORD.findall(text.lower())
    return [
        piece[index : index + 2]
        for piece in pieces
        for index in range(max(len(piece) - 1, 1))
    ]


TOKENIZERS: dict[str, Callable[[str], list[str]]] = {
    "jieba": jieba_tokens,
    "bigram": bigram_tokens,
}


def search_vector_expression(text: str, tokenizer: str = "jieba"):
    """SQL expression storing the text's tokens as a tsvector."""
    return func.to_tsvector("simple", " ".join(TOKENIZERS[tokenizer](text)))
