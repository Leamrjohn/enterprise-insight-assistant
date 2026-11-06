"""Number source sentences so a reviewer points at a boundary instead of copying it.

A copied boundary that is reworded fails the verbatim check and is lost.  A
reference can only ever resolve to the original text, so the check still holds.
"""

import re

from app.modules.reporting.semantic_review import DocumentQualificationReview

_SENTENCE_END = re.compile(r"(?<=[。！？!?；;\n])")


def number_sentences(evidences: list[dict]) -> dict[str, tuple[int, str]]:
    """Map "chunk_id.n" to that chunk's n-th sentence, counted from 1."""
    numbered: dict[str, tuple[int, str]] = {}
    for evidence in evidences:
        chunk_id = evidence.get("chunk_id")
        content = evidence.get("content")
        if not isinstance(chunk_id, int) or not isinstance(content, str):
            continue
        sentences = [part.strip() for part in _SENTENCE_END.split(content)]
        for index, sentence in enumerate(filter(None, sentences), start=1):
            numbered[f"{chunk_id}.{index}"] = (chunk_id, sentence)
    return numbered


def global_references(evidences: list[dict]) -> dict[str, tuple[int, str]]:
    """Number every sentence of all evidences S1, S2, … in evidence order.

    A plain sequence leaves no prefix to copy wrongly: a reviewer once wrote 1.8
    for 1413.8 after a prompt example, and the boundary was lost.
    """
    return {
        f"S{index}": value
        for index, value in enumerate(number_sentences(evidences).values(), start=1)
    }


def with_numbered_sentences(evidences: list[dict]) -> list[dict]:
    """The same evidences, each sentence prefixed by its reference."""
    numbered = global_references(evidences)
    by_chunk: dict[int, list[str]] = {}
    for reference, (chunk_id, sentence) in numbered.items():
        by_chunk.setdefault(chunk_id, []).append(f"[{reference}] {sentence}")
    return [
        {**evidence, "content": "\n".join(by_chunk[evidence["chunk_id"]])}
        if evidence.get("chunk_id") in by_chunk
        else evidence
        for evidence in evidences
    ]


def resolve_references(
    references: list[str], evidences: list[dict]
) -> tuple[list[DocumentQualificationReview], int]:
    """The referenced sentences, and how many references matched nothing."""
    numbered = global_references(evidences)
    resolved = []
    unknown = 0
    for reference in references:
        match = numbered.get(reference.strip())
        if match is None:
            unknown += 1
            continue
        chunk_id, sentence = match
        resolved.append(
            DocumentQualificationReview(
                statement=sentence, citation_chunk_ids=[chunk_id]
            )
        )
    return resolved, unknown
