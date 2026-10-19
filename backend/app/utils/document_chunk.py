from dataclasses import dataclass
from pathlib import Path

PARAGRAPH_CHUNK_STRATEGY = "paragraph_v1"
SLIDING_WINDOW_CHUNK_STRATEGY = "sliding_window_v1"
SUPPORTED_CHUNK_STRATEGIES = frozenset(
    {PARAGRAPH_CHUNK_STRATEGY, SLIDING_WINDOW_CHUNK_STRATEGY}
)


@dataclass(frozen=True)
class ChunkText:
    """Extracted text plus the original paragraph range (one-based)."""

    content: str
    paragraph_start: int
    paragraph_end: int


def chunk_text_with_metadata(content: str, max_tokens: int = 512) -> list[ChunkText]:
    """Split text while retaining its one-based paragraph range."""
    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
    chunks: list[ChunkText] = []
    buffer: list[str] = []
    buffer_start = 0
    token_count = 0

    for paragraph_index, paragraph in enumerate(paragraphs, start=1):
        words = paragraph.split()
        word_count = len(words)

        if word_count > max_tokens:
            if buffer:
                chunks.append(
                    ChunkText(
                        "\n\n".join(buffer),
                        buffer_start,
                        paragraph_index - 1,
                    )
                )
                buffer = []
                token_count = 0
            for start in range(0, len(words), max_tokens):
                chunks.append(
                    ChunkText(
                        " ".join(words[start : start + max_tokens]),
                        paragraph_index,
                        paragraph_index,
                    )
                )
            continue

        if token_count + word_count > max_tokens and buffer:
            chunks.append(
                ChunkText(
                    "\n\n".join(buffer),
                    buffer_start,
                    paragraph_index - 1,
                )
            )
            buffer = []
            token_count = 0

        if not buffer:
            buffer_start = paragraph_index
        buffer.append(paragraph)
        token_count += word_count

    if buffer:
        chunks.append(ChunkText("\n\n".join(buffer), buffer_start, len(paragraphs)))

    return chunks


def chunk_text(content: str, max_tokens: int = 512) -> list[str]:
    """将文本分块，每块不超过 max_tokens 个词。"""
    return [
        chunk.content
        for chunk in chunk_text_with_metadata(content, max_tokens=max_tokens)
    ]


def chunk_text_with_sliding_window(
    content: str,
    *,
    max_chars: int = 900,
    overlap_chars: int = 120,
) -> list[ChunkText]:
    """Split text into overlapping character windows while preserving paragraph bounds.

    This intentionally measures characters, not whitespace-delimited words, so a
    Chinese document without spaces still has a bounded representation.  It is a
    distinct, versioned retrieval candidate rather than a replacement for the
    paragraph-oriented baseline.
    """
    if max_chars <= 0 or not 0 <= overlap_chars < max_chars:
        raise ValueError("sliding-window bounds are invalid")
    if not content.strip():
        return []

    paragraph_starts: list[int] = []
    cursor = 0
    for raw_paragraph in content.split("\n\n"):
        start = content.find(raw_paragraph, cursor)
        cursor = start + len(raw_paragraph) + 2
        if raw_paragraph.strip():
            paragraph_starts.append(
                start + len(raw_paragraph) - len(raw_paragraph.lstrip())
            )

    def paragraph_number(position: int) -> int:
        return max(
            (
                index
                for index, start in enumerate(paragraph_starts, start=1)
                if start <= position
            ),
            default=1,
        )

    chunks: list[ChunkText] = []
    start = 0
    content_length = len(content)
    while start < content_length:
        end = min(start + max_chars, content_length)
        if end < content_length:
            boundary = max(
                content.rfind(marker, max(start + max_chars - 160, start), end)
                for marker in ("。", "！", "？", ".", "!", "?", "\n")
            )
            if boundary >= start:
                end = boundary + 1
        chunk_content = content[start:end].strip()
        if chunk_content:
            chunks.append(
                ChunkText(
                    content=chunk_content,
                    paragraph_start=paragraph_number(start),
                    paragraph_end=paragraph_number(max(start, end - 1)),
                )
            )
        if end >= content_length:
            break
        start = max(end - overlap_chars, start + 1)
    return chunks


def chunk_text_for_strategy(content: str, strategy: str) -> list[ChunkText]:
    """Return a deterministic, named chunk representation for one strategy."""
    if strategy == PARAGRAPH_CHUNK_STRATEGY:
        return chunk_text_with_metadata(content)
    if strategy == SLIDING_WINDOW_CHUNK_STRATEGY:
        return chunk_text_with_sliding_window(content)
    raise ValueError(f"unsupported chunk strategy: {strategy}")


def chunk_file(
    file_path: Path, *, include_metadata: bool = False
) -> list[str] | list[ChunkText]:
    """读取文件并分块。"""
    content = file_path.read_text(encoding="utf-8")
    if not include_metadata:
        return chunk_text(content)
    return chunk_text_with_metadata(content)
