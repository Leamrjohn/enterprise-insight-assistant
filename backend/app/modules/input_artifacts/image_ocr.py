"""Local, bounded Tesseract OCR adapter for already-inspected images."""

import csv
from dataclasses import dataclass
from pathlib import Path
from subprocess import CalledProcessError, CompletedProcess, TimeoutExpired, run
from typing import Callable


@dataclass(frozen=True, slots=True)
class ImageOcrResult:
    text: str
    mean_confidence: float | None


class ImageOcrError(RuntimeError):
    def __init__(self, error_code: str) -> None:
        super().__init__(error_code)
        self.error_code = error_code


class TesseractImageOcr:
    """Use Tesseract TSV output so confidence is retained with extracted text."""

    def __init__(
        self,
        *,
        languages: str = "chi_sim+eng",
        timeout_seconds: int = 30,
        command_runner: Callable[..., CompletedProcess[str]] = run,
    ) -> None:
        if not languages.strip() or timeout_seconds <= 0:
            raise ValueError("OCR configuration is invalid")
        self._languages = languages
        self._timeout_seconds = timeout_seconds
        self._command_runner = command_runner

    def extract(self, image_path: Path) -> ImageOcrResult:
        try:
            completed = self._command_runner(
                [
                    "tesseract",
                    str(image_path),
                    "stdout",
                    "-l",
                    self._languages,
                    "--oem",
                    "1",
                    "--psm",
                    "3",
                    "tsv",
                ],
                capture_output=True,
                check=False,
                encoding="utf-8",
                errors="replace",
                timeout=self._timeout_seconds,
            )
        except FileNotFoundError as exc:
            raise ImageOcrError("ocr_engine_unavailable") from exc
        except TimeoutExpired as exc:
            raise ImageOcrError("ocr_timeout") from exc
        except OSError as exc:
            raise ImageOcrError("ocr_engine_unavailable") from exc
        except CalledProcessError as exc:
            raise ImageOcrError("ocr_engine_failed") from exc
        if completed.returncode != 0:
            raise ImageOcrError("ocr_engine_failed")
        return _parse_tesseract_tsv(completed.stdout)


def _parse_tesseract_tsv(tsv: str) -> ImageOcrResult:
    words: list[str] = []
    confidences: list[float] = []
    for row in csv.DictReader(tsv.splitlines(), delimiter="\t"):
        text = (row.get("text") or "").strip()
        if not text:
            continue
        try:
            confidence = float(row.get("conf") or "-1")
        except ValueError:
            confidence = -1
        words.append(text)
        if confidence >= 0:
            confidences.append(confidence)
    return ImageOcrResult(
        text=" ".join(words),
        mean_confidence=(sum(confidences) / len(confidences) if confidences else None),
    )
