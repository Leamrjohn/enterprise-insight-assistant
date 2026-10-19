from subprocess import CompletedProcess, TimeoutExpired

import pytest

from app.modules.input_artifacts.pdf_render import (
    PdfPageRenderError,
    PopplerPdfPageRenderer,
)


def test_poppler_renderer_uses_one_page_and_a_bounded_output_size(tmp_path) -> None:
    source = tmp_path / "source.pdf"
    source.write_bytes(b"placeholder")
    destination = tmp_path / "page.png"
    captured: dict[str, object] = {}

    def runner(command, **kwargs):
        captured["command"] = command
        destination.write_bytes(b"png")
        return CompletedProcess(command, 0, "", "")

    result = PopplerPdfPageRenderer(
        timeout_seconds=9,
        max_side_pixels=1234,
        command_runner=runner,
    ).render_page(source, 2, destination)

    assert result == destination
    assert captured["command"] == [
        "pdftoppm",
        "-f",
        "2",
        "-l",
        "2",
        "-singlefile",
        "-png",
        "-scale-to",
        "1234",
        str(source),
        str(destination.with_suffix("")),
    ]


def test_poppler_renderer_maps_timeout_to_a_stable_error_code(tmp_path) -> None:
    source = tmp_path / "source.pdf"
    source.write_bytes(b"placeholder")

    with pytest.raises(PdfPageRenderError, match="pdf_render_timeout"):
        PopplerPdfPageRenderer(
            command_runner=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                TimeoutExpired("pdftoppm", 30)
            )
        ).render_page(source, 1, tmp_path / "page.png")
