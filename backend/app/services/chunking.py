from __future__ import annotations

from dataclasses import dataclass

from app.db.models import DocumentType
from app.services.parsers import ParsedLegalDocument
from app.services.pdf import ExtractedPage
from app.services.text import normalize_text


@dataclass(frozen=True)
class ChunkDraft:
    chunk_index: int
    text: str
    normalized_text: str
    document_type: DocumentType
    section_label: str | None
    paragraph_number: str | None
    page_start: int
    page_end: int
    char_count: int
    token_count: int


def _estimate_tokens(text: str) -> int:
    return max(1, len(text.split()))


def _split_long_text(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    pieces: list[str] = []
    cursor = 0
    while cursor < len(text):
        end = min(cursor + max_chars, len(text))
        if end < len(text):
            boundary = text.rfind(" ", cursor, end)
            if boundary > cursor + max_chars // 2:
                end = boundary
        pieces.append(text[cursor:end].strip())
        cursor = end
    return [piece for piece in pieces if piece]


def build_chunks(
    document_type: DocumentType,
    pages: list[ExtractedPage],
    parsed: ParsedLegalDocument,
    source_path: str,
    max_chars: int = 2200,
) -> list[ChunkDraft]:
    drafts: list[ChunkDraft] = []
    if (
        document_type in {DocumentType.BARE_ACT, DocumentType.RULE, DocumentType.REGULATION}
        and parsed.sections
    ):
        for section in parsed.sections:
            for part in _split_long_text(section.text, max_chars):
                drafts.append(
                    ChunkDraft(
                        chunk_index=len(drafts),
                        text=part,
                        normalized_text=normalize_text(part),
                        document_type=document_type,
                        section_label=section.label,
                        paragraph_number=None,
                        page_start=section.page_start,
                        page_end=section.page_end,
                        char_count=len(part),
                        token_count=_estimate_tokens(part),
                    )
                )
    elif (
        document_type
        in {
            DocumentType.SUPREME_COURT_JUDGMENT,
            DocumentType.HIGH_COURT_JUDGMENT,
            DocumentType.TRIBUNAL_DECISION,
            DocumentType.OTHER_LEGAL_DOCUMENT,
        }
        and parsed.paragraphs
    ):
        for paragraph in parsed.paragraphs:
            for part in _split_long_text(paragraph.text, max_chars):
                drafts.append(
                    ChunkDraft(
                        chunk_index=len(drafts),
                        text=part,
                        normalized_text=normalize_text(part),
                        document_type=document_type,
                        section_label=None,
                        paragraph_number=paragraph.official_number,
                        page_start=paragraph.page_start,
                        page_end=paragraph.page_end,
                        char_count=len(part),
                        token_count=_estimate_tokens(part),
                    )
                )
    if not drafts:
        for page in pages:
            for part in _split_long_text(page.normalized_text, max_chars):
                if not part:
                    continue
                drafts.append(
                    ChunkDraft(
                        chunk_index=len(drafts),
                        text=part,
                        normalized_text=normalize_text(part),
                        document_type=document_type,
                        section_label=None,
                        paragraph_number=None,
                        page_start=page.page_number,
                        page_end=page.page_number,
                        char_count=len(part),
                        token_count=_estimate_tokens(part),
                    )
                )
    return drafts
