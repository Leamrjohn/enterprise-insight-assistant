"""Bounded Poppler adapter for rendering one PDF page for OCR."""

from collections.abc import Callable
from pathlib import Path
from subprocess import CalledProcessError, CompletedProcess, TimeoutExpired, run


class PdfPageRenderError(RuntimeError):
    def __init__(self, error_code: str) -> None:
        super().__init__(error_code)
        self.error_code = error_code


class PopplerPdfPageRenderer:
    def __init__(
        self,
        *,
        timeout_seconds: int = 30,
        max_side_pixels: int = 2048,
        command_runner: Callable[..., CompletedProcess[str]] = run,
    ) -> None:
        if timeout_seconds <= 0 or max_side_pixels <= 0:
            raise ValueError("PDF render configuration is invalid")
        self._timeout_seconds = timeout_seconds
        self._max_side_pixels = max_side_pixels
        self._command_runner = command_runner

    def render_page(
        self,
        source_path: Path,
        page_number: int,
        destination_path: Path,
    ) -> Path:
        if page_number <= 0:
            raise ValueError("page_number must be positive")
        output_prefix = destination_path.with_suffix("")
        try:
            completed = self._command_runner(
                [
                    "pdftoppm",
                    "-f",
                    str(page_number),
                    "-l",
                    str(page_number),
                    "-singlefile",
                    "-png",
                    "-scale-to",
                    str(self._max_side_pixels),
                    str(source_path),
                    str(output_prefix),
                ],
                capture_output=True,
                check=False,
                encoding="utf-8",
                errors="replace",
                timeout=self._timeout_seconds,
            )
        except FileNotFoundError as exc:
            raise PdfPageRenderError("pdf_renderer_unavailable") from exc
        except TimeoutExpired as exc:
            raise PdfPageRenderError("pdf_render_timeout") from exc
        except OSError as exc:
            raise PdfPageRenderError("pdf_renderer_unavailable") from exc
        except CalledProcessError as exc:
            raise PdfPageRenderError("pdf_render_failed") from exc
        if completed.returncode != 0:
            raise PdfPageRenderError("pdf_render_failed")
        if not destination_path.is_file() or destination_path.stat().st_size == 0:
            raise PdfPageRenderError("pdf_render_output_missing")
        return destination_path
