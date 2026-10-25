from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from app.modules.input_artifacts.processing.parser import (
    ImageParseLimits,
    InputArtifactParseError,
    PdfParseLimits,
    XlsxParseLimits,
    parse_input_artifact_file,
)
from app.modules.input_artifacts.processing.pdf_render import PdfPageRenderError
from openpyxl import Workbook
from PIL import Image
from pypdf import PdfWriter


def test_parser_normalizes_utf8_text_and_records_document_facts(tmp_path: Path) -> None:
    source = tmp_path / "notes.md"
    source.write_bytes("\ufeff# 标题\r\n内容\r\n".encode("utf-8"))

    result = parse_input_artifact_file(
        source_path=source,
        original_filename="notes.md",
        output_directory=tmp_path / "result",
    )

    assert result.content_kind == "document"
    assert result.extracted_text_path.read_bytes() == "# 标题\r\n内容\r\n".encode()
    assert result.extracted_text_char_count == len("# 标题\r\n内容\r\n")
    assert result.manifest["source_format"] == "md"
    assert result.manifest["content_trust_level"] == "untrusted"


def test_parser_inspects_csv_without_executing_formulas(tmp_path: Path) -> None:
    source = tmp_path / "sales.csv"
    source.write_text("region,sales\neast,10\nwest,=SUM(B2:B2)\n", encoding="utf-8")

    result = parse_input_artifact_file(
        source_path=source,
        original_filename="sales.csv",
        output_directory=tmp_path / "result",
    )

    assert result.content_kind == "table"
    assert result.extracted_text_path.read_text(encoding="utf-8") == source.read_text(
        encoding="utf-8"
    )
    assert result.manifest["column_names"] == ["region", "sales"]
    assert result.manifest["data_row_count"] == 2
    assert result.manifest["formula_cell_count"] == 1
    assert result.manifest["formula_execution"] == "not_performed"
    assert result.manifest["content_trust_level"] == "untrusted"


def test_parser_rejects_unsupported_or_malformed_text_without_a_partial_result(
    tmp_path: Path,
) -> None:
    unsupported = tmp_path / "image.png"
    unsupported.write_bytes(b"not a png")
    with pytest.raises(InputArtifactParseError, match="image_structure_invalid"):
        parse_input_artifact_file(
            source_path=unsupported,
            original_filename="image.png",
            output_directory=tmp_path / "unsupported-result",
        )

    malformed = tmp_path / "broken.csv"
    malformed.write_bytes(b"name\n\xff")
    output_directory = tmp_path / "malformed-result"
    with pytest.raises(InputArtifactParseError, match="text_decode_failed"):
        parse_input_artifact_file(
            source_path=malformed,
            original_filename="broken.csv",
            output_directory=output_directory,
        )
    assert not (output_directory / "extracted.txt").exists()


def test_parser_extracts_xlsx_without_executing_formulas(tmp_path: Path) -> None:
    source = tmp_path / "sales.xlsx"
    workbook = Workbook()
    sales = workbook.active
    sales.title = "Sales"
    sales.append(["region", "sales"])
    sales.append(["east", 10])
    sales.append(["west", "=SUM(B2:B2)"])
    workbook.create_sheet("Notes").append(["owner", "finance"])
    workbook.save(source)

    result = parse_input_artifact_file(
        source_path=source,
        original_filename="sales.xlsx",
        output_directory=tmp_path / "result",
    )

    assert result.content_kind == "table"
    assert result.manifest["source_format"] == "xlsx"
    assert result.manifest["formula_cell_count"] == 1
    assert result.manifest["formula_execution"] == "not_performed"
    assert result.manifest["sheet_count"] == 2
    assert result.manifest["content_trust_level"] == "untrusted"
    extracted = result.extracted_text_path.read_text(encoding="utf-8")
    assert "# sheet: Sales" in extracted
    assert "=SUM(B2:B2)" in extracted


def test_parser_rejects_xlsx_archive_before_openpyxl_expands_it(tmp_path: Path) -> None:
    source = tmp_path / "compressed.xlsx"
    with ZipFile(source, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("xl/worksheets/sheet1.xml", "x" * 1_000)

    with pytest.raises(
        InputArtifactParseError, match="xlsx_uncompressed_budget_exceeded"
    ):
        parse_input_artifact_file(
            source_path=source,
            original_filename="compressed.xlsx",
            output_directory=tmp_path / "result",
            xlsx_limits=XlsxParseLimits(max_uncompressed_bytes=100),
        )


def test_parser_extracts_pdf_text_with_page_provenance(tmp_path: Path) -> None:
    source = tmp_path / "report.pdf"
    _write_text_pdf(source, "Quarterly revenue")

    result = parse_input_artifact_file(
        source_path=source,
        original_filename="report.pdf",
        output_directory=tmp_path / "result",
    )

    assert result.content_kind == "document"
    assert result.manifest["source_format"] == "pdf"
    assert result.manifest["content_trust_level"] == "untrusted"
    assert result.manifest["page_count"] == 1
    assert result.manifest["pages"] == [
        {"page_number": 1, "text_char_count": 17, "text_extraction_status": "text"}
    ]
    assert result.extracted_text_path.read_text(encoding="utf-8") == (
        "# page: 1\nQuarterly revenue\n"
    )


def test_parser_rejects_encrypted_or_over_page_budget_pdf(tmp_path: Path) -> None:
    encrypted = tmp_path / "encrypted.pdf"
    encrypted_writer = PdfWriter()
    encrypted_writer.add_blank_page(width=612, height=792)
    encrypted_writer.encrypt("secret")
    with encrypted.open("wb") as target:
        encrypted_writer.write(target)
    with pytest.raises(InputArtifactParseError, match="pdf_encrypted"):
        parse_input_artifact_file(
            source_path=encrypted,
            original_filename="encrypted.pdf",
            output_directory=tmp_path / "encrypted-result",
        )

    two_pages = tmp_path / "two-pages.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.add_blank_page(width=612, height=792)
    with two_pages.open("wb") as target:
        writer.write(target)
    with pytest.raises(InputArtifactParseError, match="pdf_page_budget_exceeded"):
        parse_input_artifact_file(
            source_path=two_pages,
            original_filename="two-pages.pdf",
            output_directory=tmp_path / "two-pages-result",
            pdf_limits=PdfParseLimits(max_pages=1),
        )


def test_parser_records_a_pdf_without_text_as_empty_content(tmp_path: Path) -> None:
    source = tmp_path / "scan.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    with source.open("wb") as target:
        writer.write(target)
    output_directory = tmp_path / "result"

    result = parse_input_artifact_file(
        source_path=source,
        original_filename="scan.pdf",
        output_directory=output_directory,
    )

    assert result.manifest["text_extraction_coverage"] == "empty"
    assert result.manifest["content_verification"] == "not_performed"
    assert result.manifest["pages"] == [
        {"page_number": 1, "text_char_count": 0, "text_extraction_status": "empty"}
    ]
    assert result.manifest["warnings"] == ["pdf_no_text_layer"]
    assert result.extracted_text_char_count == 0
    assert result.extracted_text_path.read_text(encoding="utf-8") == ""


def test_parser_records_a_pdf_with_missing_pages_as_partial_content(
    tmp_path: Path,
) -> None:
    source = tmp_path / "partial.pdf"
    _write_text_pdf(source, "Quarterly revenue")
    writer = PdfWriter(source)
    writer.add_blank_page(width=612, height=792)
    with source.open("wb") as target:
        writer.write(target)

    result = parse_input_artifact_file(
        source_path=source,
        original_filename="partial.pdf",
        output_directory=tmp_path / "result",
    )

    assert result.manifest["text_extraction_coverage"] == "partial"
    assert result.manifest["warnings"] == ["pdf_page_without_text"]
    assert result.manifest["pages"][1] == {
        "page_number": 2,
        "text_char_count": 0,
        "text_extraction_status": "empty",
    }


def test_parser_ocrs_only_pdf_pages_without_a_text_layer(tmp_path: Path) -> None:
    source = tmp_path / "partial.pdf"
    _write_text_pdf(source, "Quarterly revenue")
    writer = PdfWriter(source)
    writer.add_blank_page(width=612, height=792)
    with source.open("wb") as target:
        writer.write(target)
    rendered_pages: list[int] = []

    def render_page(_source: Path, page_number: int, destination: Path) -> Path:
        rendered_pages.append(page_number)
        Image.new("RGB", (20, 10), "white").save(destination)
        return destination

    result = parse_input_artifact_file(
        source_path=source,
        original_filename="partial.pdf",
        output_directory=tmp_path / "result",
        pdf_page_renderer=render_page,
        image_ocr=lambda _path: _ocr_result("Scanned appendix", 94.0),
    )

    assert rendered_pages == [2]
    assert result.manifest["text_extraction_coverage"] == "complete"
    assert result.manifest["content_verification"] == "not_performed"
    assert result.manifest["ocr_page_count"] == 1
    assert result.manifest["pages"][1] == {
        "page_number": 2,
        "text_char_count": 16,
        "text_extraction_status": "ocr",
        "ocr_mean_confidence": 94.0,
        "ocr_text_quality": "usable",
    }
    assert result.extracted_text_path.read_text(encoding="utf-8") == (
        "# page: 1\nQuarterly revenue\n# page: 2\nScanned appendix\n"
    )


def test_parser_marks_pdf_partial_when_the_ocr_page_budget_is_exhausted(
    tmp_path: Path,
) -> None:
    source = tmp_path / "scan.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.add_blank_page(width=612, height=792)
    with source.open("wb") as target:
        writer.write(target)
    rendered_pages: list[int] = []

    def render_page(_source: Path, page_number: int, destination: Path) -> Path:
        rendered_pages.append(page_number)
        Image.new("RGB", (20, 10), "white").save(destination)
        return destination

    result = parse_input_artifact_file(
        source_path=source,
        original_filename="scan.pdf",
        output_directory=tmp_path / "result",
        pdf_limits=PdfParseLimits(max_ocr_pages=1),
        pdf_page_renderer=render_page,
        image_ocr=lambda _path: _ocr_result("first page", 94.0),
    )

    assert rendered_pages == [1]
    assert result.manifest["text_extraction_coverage"] == "partial"
    assert result.manifest["warnings"] == ["pdf_ocr_page_budget_exceeded"]
    assert result.manifest["pages"][1]["text_extraction_status"] == "empty"


def test_parser_marks_low_confidence_pdf_ocr_without_discarding_its_text(
    tmp_path: Path,
) -> None:
    source = tmp_path / "scan.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    with source.open("wb") as target:
        writer.write(target)

    def render_page(_source: Path, _page_number: int, destination: Path) -> Path:
        Image.new("RGB", (20, 10), "white").save(destination)
        return destination

    result = parse_input_artifact_file(
        source_path=source,
        original_filename="scan.pdf",
        output_directory=tmp_path / "result",
        pdf_page_renderer=render_page,
        image_ocr=lambda _path: _ocr_result("uncertain digits", 32.0),
    )

    assert result.manifest["text_extraction_coverage"] == "complete"
    assert result.manifest["content_verification"] == "not_performed"
    assert result.manifest["warnings"] == ["pdf_ocr_low_confidence"]
    assert result.manifest["pages"][0]["ocr_text_quality"] == "low"
    assert result.extracted_text_path.read_text(encoding="utf-8") == (
        "# page: 1\nuncertain digits\n"
    )


def test_parser_maps_pdf_render_failures_to_stable_error_codes(tmp_path: Path) -> None:
    source = tmp_path / "scan.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    with source.open("wb") as target:
        writer.write(target)

    def render_page(_source: Path, _page_number: int, _destination: Path) -> Path:
        raise PdfPageRenderError("pdf_render_timeout")

    with pytest.raises(InputArtifactParseError, match="pdf_render_timeout"):
        parse_input_artifact_file(
            source_path=source,
            original_filename="scan.pdf",
            output_directory=tmp_path / "result",
            pdf_page_renderer=render_page,
            image_ocr=lambda _path: _ocr_result("unused", 100.0),
        )


def test_parser_extracts_image_ocr_text_and_quality(tmp_path: Path) -> None:
    source = tmp_path / "invoice.png"
    Image.new("RGB", (20, 10), "white").save(source)

    result = parse_input_artifact_file(
        source_path=source,
        original_filename="invoice.png",
        output_directory=tmp_path / "result",
        image_ocr=lambda _path: _ocr_result("发票 100 元", 91.5),
    )

    assert result.content_kind == "document"
    assert result.manifest["width"] == 20
    assert result.manifest["height"] == 10
    assert result.manifest["content_trust_level"] == "untrusted"
    assert result.manifest["ocr_text_quality"] == "usable"
    assert result.manifest["ocr_mean_confidence"] == 91.5
    assert result.extracted_text_path.read_text(encoding="utf-8") == "发票 100 元"


def test_parser_keeps_empty_or_low_confidence_image_ocr_as_quality_not_failure(
    tmp_path: Path,
) -> None:
    source = tmp_path / "scan.png"
    Image.new("RGB", (20, 10), "white").save(source)

    empty = parse_input_artifact_file(
        source_path=source,
        original_filename="scan.png",
        output_directory=tmp_path / "empty",
        image_ocr=lambda _path: _ocr_result("", None),
    )
    low = parse_input_artifact_file(
        source_path=source,
        original_filename="scan.png",
        output_directory=tmp_path / "low",
        image_ocr=lambda _path: _ocr_result("模糊文字", 32.0),
    )

    assert empty.manifest["ocr_text_quality"] == "empty"
    assert empty.manifest["warnings"] == ["image_ocr_no_text"]
    assert low.manifest["ocr_text_quality"] == "low"
    assert low.manifest["warnings"] == ["image_ocr_low_confidence"]


def test_parser_rejects_image_format_mismatch_and_pixel_budget(tmp_path: Path) -> None:
    source = tmp_path / "image.png"
    Image.new("RGB", (2, 2), "white").save(source)
    with pytest.raises(InputArtifactParseError, match="image_format_mismatch"):
        parse_input_artifact_file(
            source_path=source,
            original_filename="image.jpg",
            output_directory=tmp_path / "mismatch",
            image_ocr=lambda _path: _ocr_result("unused", 100.0),
        )
    with pytest.raises(InputArtifactParseError, match="image_pixel_budget_exceeded"):
        parse_input_artifact_file(
            source_path=source,
            original_filename="image.png",
            output_directory=tmp_path / "budget",
            image_limits=ImageParseLimits(max_pixels=3),
            image_ocr=lambda _path: _ocr_result("unused", 100.0),
        )


def test_parser_uses_original_filename_when_the_download_path_has_no_extension(
    tmp_path: Path,
) -> None:
    source = tmp_path / "raw-input"
    Image.new("RGB", (2, 2), "white").save(source, format="PNG")

    result = parse_input_artifact_file(
        source_path=source,
        original_filename="image.png",
        output_directory=tmp_path / "result",
        image_ocr=lambda _path: _ocr_result("receipt", 99.0),
    )

    assert result.manifest["source_format"] == "png"


def _ocr_result(text: str, mean_confidence: float | None):
    from app.modules.input_artifacts.processing.image_ocr import ImageOcrResult

    return ImageOcrResult(text=text, mean_confidence=mean_confidence)


def _write_text_pdf(path: Path, text: str) -> None:
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length "
        + str(len(stream)).encode("ascii")
        + b" >>\nstream\n"
        + stream
        + b"\nendstream",
    ]
    document = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for object_number, object_content in enumerate(objects, start=1):
        offsets.append(len(document))
        document.extend(f"{object_number} 0 obj\n".encode("ascii"))
        document.extend(object_content)
        document.extend(b"\nendobj\n")
    xref_offset = len(document)
    document.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    document.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        document.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    document.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode(
            "ascii"
        )
    )
    path.write_bytes(document)
