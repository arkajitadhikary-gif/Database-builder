from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from app.db.models import ResolutionStatus
from app.services.pdf import ExtractedPage

SECTION_RE = re.compile(r"(?im)^\s*(?:section\s+)?(\d+[A-Za-z]?)\.?\s+([^\n]{2,180})$")
PART_RE = re.compile(r"(?im)^\s*(PART\s+[IVXLC0-9A-Z]+)\s*[-:]?\s*(.*)$")
CHAPTER_RE = re.compile(r"(?im)^\s*(CHAPTER\s+[IVXLC0-9A-Z]+)\s*[-:]?\s*(.*)$")
PARAGRAPH_RE = re.compile(r"(?m)^\s*(?:\[(\d+[A-Za-z]?)\]|(\d+[A-Za-z]?)[.)])\s+(.+)$")
CITATION_RE = re.compile(
    r"\b(?:AIR|SCC|SCR|ALL\s+ER|ILR)\s*\(?\s*\d{4}\s*\)?\s*[^\n,;]{0,80}", re.I
)
STATUTE_REF_RE = re.compile(
    r"\b(?:section|sec\.?|article|art\.?)\s+([0-9]+[A-Za-z]?(?:\([^)]+\))?)\s+(?:of\s+the\s+)?([^,;.\n]{3,120})",
    re.I,
)


@dataclass(frozen=True)
class ParsedSection:
    label: str
    heading: str | None
    text: str
    page_start: int
    page_end: int
    parent_label: str | None = None


@dataclass(frozen=True)
class ParsedPart:
    label: str
    title: str | None
    page_start: int
    page_end: int


@dataclass(frozen=True)
class ParsedChapter:
    label: str
    title: str | None
    page_start: int
    page_end: int
    part_label: str | None


@dataclass(frozen=True)
class ParsedParagraph:
    official_number: str | None
    internal_sequence: int
    text: str
    page_start: int
    page_end: int


@dataclass(frozen=True)
class ParsedReference:
    source_text: str
    reference_type: str
    normalized_key: str | None
    resolution_status: ResolutionStatus
    page_start: int
    page_end: int


@dataclass(frozen=True)
class ParsedLegalDocument:
    title: str | None
    year: int | None
    parts: list[ParsedPart]
    chapters: list[ParsedChapter]
    sections: list[ParsedSection]
    paragraphs: list[ParsedParagraph]
    references: list[ParsedReference]
    case_title: str | None = None
    court: str | None = None
    case_number: str | None = None
    decision_date: date | None = None
    coram_text: str | None = None


def _joined_pages(pages: list[ExtractedPage]) -> str:
    return "\n\n".join(page.normalized_text for page in pages)


def _page_for_offset(pages: list[ExtractedPage], offset: int) -> int:
    cursor = 0
    for page in pages:
        end = cursor + len(page.normalized_text)
        if offset <= end:
            return page.page_number
        cursor = end + 2
    return pages[-1].page_number


def parse_legislation(pages: list[ExtractedPage]) -> ParsedLegalDocument:
    full_text = _joined_pages(pages)
    parts = [
        ParsedPart(
            label=match.group(1).strip(),
            title=match.group(2).strip() or None,
            page_start=_page_for_offset(pages, match.start()),
            page_end=_page_for_offset(pages, match.end()),
        )
        for match in PART_RE.finditer(full_text)
    ]
    chapters = [
        ParsedChapter(
            label=match.group(1).strip(),
            title=match.group(2).strip() or None,
            page_start=_page_for_offset(pages, match.start()),
            page_end=_page_for_offset(pages, match.end()),
            part_label=parts[-1].label
            if parts and parts[-1].page_start <= _page_for_offset(pages, match.start())
            else None,
        )
        for match in CHAPTER_RE.finditer(full_text)
    ]
    section_matches = list(SECTION_RE.finditer(full_text))
    sections: list[ParsedSection] = []
    for index, match in enumerate(section_matches):
        start = match.start()
        end = (
            section_matches[index + 1].start()
            if index + 1 < len(section_matches)
            else len(full_text)
        )
        section_text = full_text[start:end].strip()
        sections.append(
            ParsedSection(
                label=match.group(1),
                heading=match.group(2).strip() or None,
                text=section_text,
                page_start=_page_for_offset(pages, start),
                page_end=_page_for_offset(pages, end),
            )
        )
    # Contents pages and repeated schedules can contain the same section label
    # more than once. The database intentionally keys sections by act + label,
    # so keep the richest occurrence instead of crashing the ingestion job.
    deduplicated_sections: dict[str, ParsedSection] = {}
    for section in sections:
        current = deduplicated_sections.get(section.label)
        if current is None or len(section.text) > len(current.text):
            deduplicated_sections[section.label] = section
    sections = list(deduplicated_sections.values())
    references = extract_references(pages)
    title = next((line.strip() for line in full_text.splitlines() if len(line.strip()) >= 5), None)
    year_match = re.search(r"\b(18|19|20)\d{2}\b", full_text[:3000])
    return ParsedLegalDocument(
        title=title,
        year=int(year_match.group(0)) if year_match else None,
        parts=parts,
        chapters=chapters,
        sections=sections,
        paragraphs=[],
        references=references,
    )


def parse_judgment(pages: list[ExtractedPage]) -> ParsedLegalDocument:
    full_text = _joined_pages(pages)
    paragraphs: list[ParsedParagraph] = []
    matches = list(PARAGRAPH_RE.finditer(full_text))
    for sequence, match in enumerate(matches, start=1):
        official = match.group(1) or match.group(2)
        start = match.start()
        end = matches[sequence].start() if sequence < len(matches) else len(full_text)
        paragraphs.append(
            ParsedParagraph(
                official_number=official,
                internal_sequence=sequence,
                text=full_text[start:end].strip(),
                page_start=_page_for_offset(pages, start),
                page_end=_page_for_offset(pages, end),
            )
        )
    court_match = re.search(r"(?im)^\s*(SUPREME COURT|HIGH COURT|TRIBUNAL)[^\n]*$", full_text)
    case_match = re.search(r"(?im)^\s*(?:case|civil|criminal|writ|appeal)[^\n]{0,160}$", full_text)
    date_match = re.search(r"\b(\d{1,2}[/-]\d{1,2}[/-](?:19|20)\d{2})\b", full_text)
    return ParsedLegalDocument(
        title=next(
            (line.strip() for line in full_text.splitlines() if len(line.strip()) > 8), None
        ),
        year=None,
        parts=[],
        chapters=[],
        sections=[],
        paragraphs=paragraphs,
        references=extract_references(pages),
        court=court_match.group(1).title() if court_match else None,
        case_number=case_match.group(0).strip() if case_match else None,
        decision_date=_parse_date(date_match.group(1)) if date_match else None,
    )


def _parse_date(value: str) -> date | None:
    for separator in ("/", "-"):
        parts = value.split(separator)
        if len(parts) == 3:
            day, month, year = map(int, parts)
            try:
                return date(year, month, day)
            except ValueError:
                return None
    return None


def extract_references(pages: list[ExtractedPage]) -> list[ParsedReference]:
    full_text = _joined_pages(pages)
    results: list[ParsedReference] = []
    for pattern, reference_type in ((STATUTE_REF_RE, "STATUTORY"), (CITATION_RE, "CASE_CITATION")):
        for match in pattern.finditer(full_text):
            source_text = match.group(0).strip()
            normalized = re.sub(r"\s+", " ", source_text).casefold()
            results.append(
                ParsedReference(
                    source_text=source_text,
                    reference_type=reference_type,
                    normalized_key=normalized,
                    resolution_status=ResolutionStatus.UNRESOLVED,
                    page_start=_page_for_offset(pages, match.start()),
                    page_end=_page_for_offset(pages, match.end()),
                )
            )
    return results
