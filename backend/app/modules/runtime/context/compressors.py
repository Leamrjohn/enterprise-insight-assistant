"""Section compressors (C4): code only, so nothing is reworded.

Each takes one section's value and returns a shorter one, or the same value
when there is nothing to shorten.  The engine compares the two to decide
whether the section counts as compressed.
"""

from __future__ import annotations

import re
from typing import Any

from app.modules.documents.search_tokens import jieba_tokens

# The latest exchange is always sent whole.
HISTORY_RECENT_MESSAGES = 2
# Older assistant replies are cut to this many characters.
ASSISTANT_REPLY_CHARS = 80


def compress_history(conversation_context: Any) -> Any:
    """Shorten older assistant replies; never drop or cut what the user said.

    A user's scope ("only East China from now on") can sit in any turn the
    conversation service selected, and only some of those reach
    standing_constraints, so dropping turns could lose one silently.  If the
    history still does not fit, the Planner asks back instead (clarify).
    """
    if not isinstance(conversation_context, dict):
        return conversation_context
    messages = conversation_context.get("messages") or []
    older = messages[:-HISTORY_RECENT_MESSAGES]
    if not any(_is_long_reply(m) for m in older):
        return conversation_context
    shortened = [
        {
            **m,
            "content": m["content"][:ASSISTANT_REPLY_CHARS],
            "content_truncated": True,
        }
        if _is_long_reply(m)
        else m
        for m in older
    ]
    return {
        **conversation_context,
        "messages": [*shortened, *messages[-HISTORY_RECENT_MESSAGES:]],
        "history_truncated": True,
    }


def _is_long_reply(message: dict) -> bool:
    return (
        message.get("role") == "assistant"
        and len(message.get("content", "")) > ASSISTANT_REPLY_CHARS
    )


# C7: marks where an evidence excerpt left sentences out.
ELISION = "……"
# A sentence ends at 。！？；or a line break; the last one may end the text.
_SENTENCE = re.compile(r"[^。！？；\n]*(?:[。！？；]+|\n+|$)")
# Codes such as CUST-0001 or SUP-003.
_ENTITY = re.compile(r"[A-Za-z]{2,}-\d+")


def split_sentences(text: str) -> list[str]:
    """The text's sentences with their own punctuation; they join back to it."""
    return [sentence for sentence in _SENTENCE.findall(text) if sentence]


def question_terms(question: str) -> tuple[set[str], set[str]]:
    """(words, entity codes) from the question, both lower case."""
    entities = {entity.lower() for entity in _ENTITY.findall(question)}
    return set(jieba_tokens(question)), entities


def sentence_score(sentence: str, *, terms: set[str], entities: set[str]) -> int:
    """How much of the question one evidence sentence speaks to.

    Each entity code found in the sentence adds 3, each question word adds 1,
    and a sentence that already scored gets 1 more for holding a number: a
    number alone says nothing about the question.  Matching ignores case.
    """
    lowered = sentence.lower()
    score = 3 * sum(entity in lowered for entity in entities)
    score += sum(term in lowered for term in terms)
    if score and any(char.isdigit() for char in sentence):
        score += 1
    return score


def excerpt(text: str, question: str, max_chars: int) -> str | None:
    """The question's sentences from ``text`` within ``max_chars``, or None.

    Sentences are taken by score (ties: the earlier one) while the excerpt
    fits, then joined in their original order with ELISION wherever something
    was left out; every kept sentence is copied verbatim, so no number changes.
    None when no sentence scores or none fits.
    """
    sentences = split_sentences(text)
    terms, entities = question_terms(question)
    scores = [
        sentence_score(sentence, terms=terms, entities=entities)
        for sentence in sentences
    ]
    kept: set[int] = set()
    for index in sorted(
        (i for i, score in enumerate(scores) if score > 0),
        key=lambda i: (-scores[i], i),
    ):
        if len(_join(sentences, kept | {index})) <= max_chars:
            kept.add(index)
    return _join(sentences, kept) if kept else None


def _join(sentences: list[str], kept: set[int]) -> str:
    parts: list[str] = []
    previous = -1
    for index in sorted(kept):
        if index != previous + 1:
            parts.append(ELISION)
        parts.append(sentences[index])
        previous = index
    if previous != len(sentences) - 1:
        parts.append(ELISION)
    return "".join(parts)
