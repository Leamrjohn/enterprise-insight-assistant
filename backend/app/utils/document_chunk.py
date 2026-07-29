from pathlib import Path
from dataclasses import dataclass


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


def chunk_file(
    file_path: Path, *, include_metadata: bool = False
) -> list[str] | list[ChunkText]:
    """读取文件并分块。"""
    content = file_path.read_text(encoding="utf-8")
    if not include_metadata:
        return chunk_text(content)
    return chunk_text_with_metadata(content)
