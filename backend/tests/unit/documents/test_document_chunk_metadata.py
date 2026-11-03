from app.utils.document_chunk import (
    PASSAGE_CHUNK_STRATEGY,
    SLIDING_WINDOW_CHUNK_STRATEGY,
    ChunkText,
    chunk_file,
    chunk_text_for_strategy,
    chunk_text_with_passages,
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


def test_passages_bound_chinese_text_that_has_no_spaces() -> None:
    content = "# 制度\n\n" + "。".join(["这是一段没有空格的中文内容"] * 60) + "。"

    chunks = chunk_text_with_passages(content)

    assert len(chunks) > 1
    assert all(len(chunk.content) <= 160 + 10 for chunk in chunks)


def test_every_passage_says_which_document_and_section_it_came_from() -> None:
    content = (
        "# 供应商评估-深圳传动\n\n> 文档编号：DOC-SE-0004\n\n# 年度评估报告\n\n"
        "## 一、概况\n\n深圳传动（供应商编码：SUP-012）位于深圳。\n\n"
        "## 二、质量\n\n本年度质量评分为 4.20/5.0。"
    )

    chunks = chunk_text_with_passages(content)

    quality = next(chunk for chunk in chunks if "4.20" in chunk.content)
    assert "供应商评估-深圳传动" in quality.content
    assert "SUP-012" in quality.content
    assert "二、质量" in quality.content
    assert "一、概况" not in quality.content


def test_passages_do_not_carry_one_documents_title_into_the_next() -> None:
    content = (
        "# 甲公司报告\n\n编号 SUP-001 的内容。\n\n# 乙公司报告\n\n编号 SUP-002 的内容。"
    )

    first, second = chunk_text_with_passages(content)

    assert "甲公司报告" in first.content and "SUP-002" not in first.content
    assert "乙公司报告" in second.content and "SUP-001" not in second.content


def test_each_piece_of_a_cut_table_keeps_its_header() -> None:
    rows = "\n".join(f"| 客户{i} | {i} |" for i in range(40))
    content = f"# 表\n\n| 客户 | 金额 |\n|---|---|\n{rows}"

    chunks = chunk_text_with_passages(content)

    assert len(chunks) > 1
    assert all("| 客户 | 金额 |" in chunk.content for chunk in chunks)
    assert "| 客户39 | 39 |" in chunks[-1].content


def test_passages_keep_paragraph_numbers_and_every_line_of_the_body() -> None:
    content = "# 题\n\n第一段内容。\n\n第二段内容。"

    chunks = chunk_text_with_passages(content)

    assert (chunks[0].paragraph_start, chunks[-1].paragraph_end) == (2, 3)
    assert "第一段内容。" in chunks[0].content
    assert "第二段内容。" in chunks[-1].content


def test_empty_text_has_no_passages_and_the_strategy_is_registered() -> None:
    assert chunk_text_with_passages(" \n\n ") == []
    assert chunk_text_for_strategy("# 题\n\n内容。", PASSAGE_CHUNK_STRATEGY)


def test_front_matter_with_text_does_not_swallow_the_first_real_document() -> None:
    content = (
        "# 资料汇编\n\n## 保密声明\n本文件仅供内部使用。\n\n"
        "# 2024年1月事实包\n\n销售额 100 元。"
    )

    chunks = chunk_text_with_passages(content)

    answer = next(chunk for chunk in chunks if "销售额" in chunk.content)
    assert "2024年1月事实包" in answer.content
    assert "资料汇编" not in answer.content
