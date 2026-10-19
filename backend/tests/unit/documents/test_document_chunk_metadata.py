from app.utils.document_chunk import (
    SLIDING_WINDOW_CHUNK_STRATEGY,
    ChunkText,
    chunk_file,
    chunk_text_for_strategy,
)


def test_chunk_file_preserves_paragraph_ranges(tmp_path) -> None:
    source = tmp_path / "report.txt"
    source.write_text("标题\n第一段\n\n第二段\n\n第三段", encoding="utf-8")

    chunks = chunk_file(source, include_metadata=True)

    assert chunks == [ChunkText("标题\n第一段\n\n第二段\n\n第三段", 1, 3)]


def test_chunk_file_splits_long_paragraph_without_losing_its_range(tmp_path) -> None:
    source = tmp_path / "report.txt"
    source.write_text(
        " ".join(f"word-{index}" for index in range(513)), encoding="utf-8"
    )

    chunks = chunk_file(source, include_metadata=True)

    assert [chunk.paragraph_start for chunk in chunks] == [1, 1]
    assert [chunk.paragraph_end for chunk in chunks] == [1, 1]
    assert [len(chunk.content.split()) for chunk in chunks] == [512, 1]


def test_sliding_window_strategy_bounds_unspaced_chinese_text_with_overlap() -> None:
    content = "第一段。" + "甲" * 950 + "\n\n第二段。" + "乙" * 950

    chunks = chunk_text_for_strategy(content, SLIDING_WINDOW_CHUNK_STRATEGY)

    assert len(chunks) >= 3
    assert all(len(chunk.content) <= 900 for chunk in chunks)
    assert chunks[0].paragraph_start == 1
    assert chunks[-1].paragraph_end == 2
    assert chunks[0].content[-120:] in chunks[1].content
