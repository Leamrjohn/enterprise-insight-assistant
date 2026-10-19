from subprocess import CompletedProcess, TimeoutExpired

import pytest

from app.modules.input_artifacts.image_ocr import ImageOcrError, TesseractImageOcr


def test_tesseract_ocr_retains_text_and_mean_word_confidence(tmp_path) -> None:
    image = tmp_path / "input.png"
    image.write_bytes(b"placeholder")
    tsv = (
        "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
        "5\t1\t1\t1\t1\t1\t0\t0\t1\t1\t92.0\t发票\n"
        "5\t1\t1\t1\t1\t2\t0\t0\t1\t1\t88.0\t100\n"
    )
    ocr = TesseractImageOcr(
        command_runner=lambda *_args, **_kwargs: CompletedProcess([], 0, tsv, "")
    )

    result = ocr.extract(image)

    assert result.text == "发票 100"
    assert result.mean_confidence == 90.0


def test_tesseract_ocr_maps_timeout_to_a_stable_error_code(tmp_path) -> None:
    image = tmp_path / "input.png"
    image.write_bytes(b"placeholder")
    ocr = TesseractImageOcr(
        command_runner=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            TimeoutExpired("tesseract", 30)
        )
    )

    with pytest.raises(ImageOcrError, match="ocr_timeout"):
        ocr.extract(image)
