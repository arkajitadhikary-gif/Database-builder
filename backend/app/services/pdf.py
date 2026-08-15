from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import fitz

from app.core.config import get_settings
from app.db.models import ExtractionMethod
from app.services.discovery import validate_pdf
from app.services.text import normalize_text


@dataclass(frozen=True)
class ExtractedPage:
    page_number: int
    raw_text: str
    normalized_text: str
    extraction_method: ExtractionMethod
    warnings: list[str]
    ocr_engine: str | None = None
    ocr_confidence: float | None = None


@dataclass(frozen=True)
class ExtractedDocument:
    page_count: int
    pages: list[ExtractedPage]
    needs_ocr: bool


def extract_pdf(path: Path, max_bytes: int | None = None) -> ExtractedDocument:
    valid, reason = validate_pdf(path, max_bytes=max_bytes)
    if not valid:
        raise ValueError(reason)
    pages: list[ExtractedPage] = []
    with fitz.open(path) as pdf:
        for index, page in enumerate(pdf):
            raw_text = page.get_text("text")
            normalized = normalize_text(raw_text)
            warnings: list[str] = []
            if not normalized:
                warnings.append("empty text extraction")
            elif len(normalized) < 40:
                warnings.append("low text volume")
            pages.append(
                ExtractedPage(
                    page_number=index + 1,
                    raw_text=raw_text,
                    normalized_text=normalized,
                    extraction_method=ExtractionMethod.TEXT,
                    warnings=warnings,
                )
            )
    if not pages:
        raise ValueError("PDF contains no pages")
    needs_ocr = sum(1 for page in pages if not page.normalized_text) >= max(1, len(pages) // 2)
    return ExtractedDocument(page_count=len(pages), pages=pages, needs_ocr=needs_ocr)


def resolve_executable(name: str) -> str | None:
    resolved = shutil.which(name)
    if resolved:
        return resolved

    candidates: list[Path] = []
    venv_bin = Path(sys.executable).resolve().parent
    if venv_bin.exists():
        candidates.append(venv_bin)

    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if entry:
            path = Path(entry).expanduser()
            if path.exists() and path not in candidates:
                candidates.append(path)

    for directory in candidates:
        for suffix in ("", ".exe", ".cmd", ".bat"):
            candidate = (directory / name).with_suffix(suffix if suffix else "")
            if candidate.exists():
                return str(candidate)
            if suffix:
                windows_name = f"{name}{suffix}"
                candidate = directory / windows_name
                if candidate.exists():
                    return str(candidate)
    return None


def ocr_available() -> tuple[bool, str]:
    ocrmypdf = resolve_executable("ocrmypdf")
    tesseract = resolve_executable("tesseract")
    if ocrmypdf and tesseract:
        return True, f"ocrmypdf={ocrmypdf}; tesseract={tesseract}"
    missing = []
    if not ocrmypdf:
        missing.append("ocrmypdf")
    if not tesseract:
        missing.append("tesseract")
    return False, "missing " + ", ".join(missing)


def extract_with_ocr(path: Path, timeout_seconds: int | None = None) -> ExtractedDocument:
    settings = get_settings()
    if not settings.ocr_enabled:
        raise RuntimeError("OCR is disabled by configuration")
    available, detail = ocr_available()
    if not available:
        raise RuntimeError(f"OCR is not configured: {detail}")
    timeout = timeout_seconds or settings.ocr_timeout_seconds
    original = extract_pdf(path, max_bytes=settings.max_pdf_bytes)
    ocrmypdf_path = resolve_executable("ocrmypdf")
    if not ocrmypdf_path:
        raise RuntimeError("OCR is not configured: missing ocrmypdf")
    with tempfile.TemporaryDirectory(prefix="judicore-ocr-") as directory:
        output = Path(directory) / "ocr.pdf"
        command = [
            ocrmypdf_path,
            "--skip-text",
            "--deskew",
            "--output-type",
            "pdf",
            str(path),
            str(output),
        ]
        try:
            completed = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("OCR process timed out") from exc
        except subprocess.CalledProcessError as exc:
            detail_text = (exc.stderr or exc.stdout or "OCR failed")[-2000:]
            raise RuntimeError(detail_text) from exc
        result = extract_pdf(output)
    pages = []
    for original_page, page in zip(original.pages, result.pages, strict=True):
        original_needs_ocr = not original_page.normalized_text or (
            len(original_page.normalized_text) < 40
        )
        method = (
            ExtractionMethod.MIXED
            if original_needs_ocr and original_page.normalized_text
            else (
                ExtractionMethod.OCR if original_needs_ocr else ExtractionMethod.TEXT
            )
        )
        pages.append(
            ExtractedPage(
                page_number=page.page_number,
                raw_text=page.raw_text,
                normalized_text=page.normalized_text,
                extraction_method=method,
                warnings=page.warnings,
                ocr_engine=f"ocrmypdf; {completed.args[0]}" if original_needs_ocr else None,
            )
        )
    return ExtractedDocument(result.page_count, pages, needs_ocr=False)
