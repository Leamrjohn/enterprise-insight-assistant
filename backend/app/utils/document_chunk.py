import re
from dataclasses import dataclass
from pathlib import Path

PARAGRAPH_CHUNK_STRATEGY = "paragraph_v1"
SLIDING_WINDOW_CHUNK_STRATEGY = "sliding_window_v1"
PASSAGE_CHUNK_STRATEGY = "passage_v1"
SUPPORTED_CHUNK_STRATEGIES = frozenset(
    {PARAGRAPH_CHUNK_STRATEGY, SLIDING_WINDOW_CHUNK_STRATEGY, PASSAGE_CHUNK_STRATEGY}
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


# The local embedding model reads about 128 tokens, roughly 220 Chinese characters.
MAX_PASSAGE_BODY_CHARS = 160
MAX_PASSAGE_TITLE_CHARS = 40
MAX_PASSAGE_HEADING_CHARS = 24
MAX_PASSAGE_IDENTIFIERS = 3
_IDENTIFIER = re.compile(r"[A-Z]{2,}-\d[\dA-Z-]*")
_SENTENCE_END = re.compile(r"(?<=[。！？；;])")
_PADDED_MONTH = re.compile(r"(\d{4}年)0(\d月)")


def _title_sections(paragraphs: list[str]) -> list[list[tuple[int, str]]]:
    """Group numbered paragraphs under their top-level title.

    A second title straight after the first, with no body between them, is the
    same document's cover, so it does not start a new section.
    """
    sections: list[list[tuple[int, str]]] = [[]]
    has_body = False
    for number, paragraph in enumerate(paragraphs, start=1):
        if paragraph.startswith("# ") and has_body:
            sections.append([])
            has_body = False
        sections[-1].append((number, paragraph))
        # A heading with text under it in the same paragraph is body too.
        is_cover_line = paragraph.startswith((">", "---")) or (
            paragraph.startswith("#") and "\n" not in paragraph
        )
        has_body = has_body or not is_cover_line
    return sections


def _section_context(section: list[tuple[int, str]]) -> tuple[str, str]:
    title = next(
        (text[2:].split("\n", 1)[0].strip() for _, text in section if text[:2] == "# "),
        "",
    )
    text = "\n".join(paragraph for _, paragraph in section)
    identifiers = list(dict.fromkeys(_IDENTIFIER.findall(text)))
    return (
        title[:MAX_PASSAGE_TITLE_CHARS],
        " ".join(identifiers[:MAX_PASSAGE_IDENTIFIERS]),
    )


def _split_line(line: str, max_chars: int) -> list[str]:
    """Keep a line whole when it fits; otherwise cut at sentence ends, then by length."""
    if len(line) <= max_chars:
        return [line]
    pieces: list[str] = []
    for sentence in _SENTENCE_END.split(line):
        while len(sentence) > max_chars:
            pieces.append(sentence[:max_chars])
            sentence = sentence[max_chars:]
        if sentence.strip():
            pieces.append(sentence)
    return pieces


def _body_units(lines: list[str], max_chars: int) -> tuple[list[str], str]:
    """The units to pack, and the header a table's pieces must each repeat."""
    is_table = len(lines) >= 2 and all(line.startswith("|") for line in lines[:2])
    header = "\n".join(lines[:2]) if is_table else ""
    rows = lines[2:] if is_table else lines
    limit = max_chars - len(header) - 1 if header else max_chars
    return [
        piece for line in rows for piece in _split_line(line, max(limit, 1))
    ], header


def _section_passages(
    section: list[tuple[int, str]], max_chars: int
) -> list[ChunkText]:
    title, identifiers = _section_context(section)
    chunks: list[ChunkText] = []
    heading = ""
    table_header = ""
    buffer: list[str] = []
    start = end = 0

    def flush() -> None:
        if not buffer:
            return
        # Under the title with no section yet, the heading is the title itself.
        parts = (title, identifiers, "" if heading == title else heading)
        label = "｜".join(part for part in parts if part)
        # People ask about 2025年7月 or 2025年07月, so the label says both.
        label = _PADDED_MONTH.sub(r"\1\2（\g<0>）", label)
        body = "\n".join(([table_header] if table_header else []) + buffer)
        chunks.append(ChunkText(f"{label}\n{body}" if label else body, start, end))
        buffer.clear()

    for number, paragraph in section:
        lines = [line.strip() for line in paragraph.split("\n") if line.strip()]
        if lines[0].startswith("#"):
            flush()
            heading = lines[0].lstrip("# ").strip()[:MAX_PASSAGE_HEADING_CHARS]
            lines = lines[1:]
        if not lines or lines[0] == "---" or lines[0].startswith(">"):
            continue
        units, header = _body_units(lines, max_chars)
        if header != table_header:
            flush()
            table_header = header
        room = max_chars - len(table_header)
        for unit in units:
            if buffer and len("\n".join([*buffer, unit])) > room:
                flush()
            if not buffer:
                start = number
            buffer.append(unit)
            end = number
    flush()
    return chunks


def chunk_text_with_passages(
    content: str, *, max_chars: int = MAX_PASSAGE_BODY_CHARS
) -> list[ChunkText]:
    """Split text into short passages that each say which document they came from.

    Length is counted in characters, so Chinese text is really bounded, and short
    enough for the embedding model to read all of it.  Cutting a document apart
    loses what its opening said, so every passage repeats the title, the section
    heading and the document's identifiers.
    """
    if max_chars <= 0:
        raise ValueError("passage bound is invalid")
    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
    return [
        chunk
        for section in _title_sections(paragraphs)
        for chunk in _section_passages(section, max_chars)
    ]


def chunk_text_for_strategy(content: str, strategy: str) -> list[ChunkText]:
    """Return a deterministic, named chunk representation for one strategy."""
    if strategy == PARAGRAPH_CHUNK_STRATEGY:
        return chunk_text_with_metadata(content)
    if strategy == SLIDING_WINDOW_CHUNK_STRATEGY:
        return chunk_text_with_sliding_window(content)
    if strategy == PASSAGE_CHUNK_STRATEGY:
        return chunk_text_with_passages(content)
    raise ValueError(f"unsupported chunk strategy: {strategy}")


def chunk_file(
    file_path: Path, *, include_metadata: bool = False
) -> list[str] | list[ChunkText]:
    """读取文件并分块。"""
    content = file_path.read_text(encoding="utf-8")
    if not include_metadata:
        return chunk_text(content)
    return chunk_text_with_metadata(content)
