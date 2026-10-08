from pathlib import Path

import fitz
import pytest

from app.db.models import DocumentType, ExtractionMethod, ResolutionStatus
from app.services.chunking import build_chunks
from app.services.discovery import sha256_file, validate_pdf
from app.services.parsers import parse_judgment, parse_legislation
from app.services.pdf import extract_pdf
from app.services.text import classify_document, normalize_text


def make_pdf(path: Path, pages: list[str]) -> None:
    document = fitz.open()
    for text in pages:
        page = document.new_page()
        page.insert_text((72, 72), text)
    document.save(path)
    document.close()


def test_sha256_and_pdf_validation(tmp_path: Path) -> None:
    path = tmp_path / "source.pdf"
    make_pdf(path, ["Section 1 Short title\nThis is a source page."])
    valid, reason = validate_pdf(path)
    assert valid is True
    assert reason == "valid PDF header"
    assert len(sha256_file(path)) == 64


def test_invalid_pdf_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "not-a-pdf.pdf"
    path.write_bytes(b"not a PDF")
    valid, reason = validate_pdf(path)
    assert valid is False
    assert "PDF header" in reason


def test_normalization_is_conservative() -> None:
    assert normalize_text(" a  b\r\n\r\n\r\nc\x00 ") == "a b\n\nc"


def test_classification_is_source_derived() -> None:
    classification = classify_document("SUPREME COURT OF INDIA\nJudgment dated 01/01/2020")
    assert classification.document_type == DocumentType.SUPREME_COURT_JUDGMENT
    assert classification.confidence > 0
    assert classification.signals


def test_legislation_parsing_preserves_page_ranges(tmp_path: Path) -> None:
    path = tmp_path / "act.pdf"
    make_pdf(
        path,
        [
            "THE SAMPLE ACT, 2020\nPART I\nCHAPTER I\n1. Short title\nThis Act applies.",
            "2. Definitions\nIn this Act, section means a provision.\nSection 1 of the Act.",
        ],
    )
    extracted = extract_pdf(path)
    parsed = parse_legislation(extracted.pages)
    assert parsed.sections
    assert parsed.sections[0].page_start == 1
    assert parsed.sections[-1].page_end == 2
    assert parsed.references
    assert parsed.references[0].resolution_status == ResolutionStatus.UNRESOLVED
    chunks = build_chunks(DocumentType.BARE_ACT, extracted.pages, parsed, str(path))
    assert chunks
    assert all(chunk.page_start >= 1 for chunk in chunks)
    assert any(chunk.page_end == 2 for chunk in chunks)


def test_legislation_parser_deduplicates_repeated_section_labels(tmp_path: Path) -> None:
    path = tmp_path / "duplicate-sections.pdf"
    make_pdf(
        path,
        ["CONTENTS\n1. Short title\n\n1. Short title\nThis is the operative text."],
    )
    parsed = parse_legislation(extract_pdf(path).pages)
    assert [section.label for section in parsed.sections] == ["1"]
    assert "operative text" in parsed.sections[0].text


def test_judgment_parsing_uses_official_and_internal_numbers(tmp_path: Path) -> None:
    path = tmp_path / "judgment.pdf"
    make_pdf(
        path,
        ["HIGH COURT OF SAMPLE\n[1] The court considered the record.\n[2] The appeal is allowed."],
    )
    extracted = extract_pdf(path)
    parsed = parse_judgment(extracted.pages)
    assert len(parsed.paragraphs) == 2
    assert parsed.paragraphs[0].official_number == "1"
    assert parsed.paragraphs[1].internal_sequence == 2
    assert parsed.paragraphs[0].page_start == parsed.paragraphs[1].page_start == 1


def test_extraction_tracks_each_page(tmp_path: Path) -> None:
    path = tmp_path / "multi.pdf"
    make_pdf(path, ["first page", "second page"])
    extracted = extract_pdf(path)
    assert extracted.page_count == 2
    assert [page.page_number for page in extracted.pages] == [1, 2]
    assert all(page.extraction_method == ExtractionMethod.TEXT for page in extracted.pages)


def test_search_rejects_whitespace_only_queries() -> None:
    from pydantic import ValidationError

    from app.schemas.api import SearchRequest

    with pytest.raises(ValidationError):
        SearchRequest(query="   ")


def test_ocr_respects_disabled_configuration(monkeypatch) -> None:
    from app.core.config import get_settings
    from app.services.pdf import extract_with_ocr

    settings = get_settings()
    monkeypatch.setattr(settings, "ocr_enabled", False)
    with pytest.raises(RuntimeError, match="disabled by configuration"):
        extract_with_ocr(Path("does-not-exist.pdf"))


def test_document_integrity_constraints_are_declared() -> None:
    from app.db.models import Document

    names = {constraint.name for constraint in Document.__table__.constraints}
    assert "ck_documents_byte_size_positive" in names
    assert "ck_documents_page_count_positive" in names
    assert "ck_documents_classification_confidence_range" in names


def test_discovery_limit_is_enforced(tmp_path: Path) -> None:
    from app.services.discovery import discover_paths

    for index in range(3):
        (tmp_path / f"{index}.pdf").write_bytes(b"%PDF-")
    with pytest.raises(ValueError, match="discovery limit exceeded"):
        discover_paths([str(tmp_path)], recursive=False, max_files=2)


def test_pdf_size_limit_is_enforced(tmp_path: Path) -> None:
    path = tmp_path / "large.pdf"
    path.write_bytes(b"%PDF-12345")
    valid, reason = validate_pdf(path, max_bytes=5)
    assert valid is False
    assert "size limit" in reason
