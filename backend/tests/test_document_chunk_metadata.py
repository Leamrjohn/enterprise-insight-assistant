from app.utils.document_chunk import ChunkText, chunk_file


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
