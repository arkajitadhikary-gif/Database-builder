from __future__ import annotations

import asyncio
import shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.db.models import (
    Act,
    Chunk,
    Document,
    DocumentType,
    DuplicateKind,
    DuplicateRecord,
    Embedding,
    IngestionBatch,
    IngestionError,
    IngestionItem,
    IngestionState,
    Judgment,
    JudgmentParagraph,
    LegalChapter,
    LegalPart,
    LegalSection,
    Page,
    Reference,
    Source,
    StageEvent,
)
from app.db.session import SessionFactory
from app.services.chunking import build_chunks
from app.services.discovery import sha256_file, sha256_text, validate_pdf
from app.services.embeddings import get_embedding_provider
from app.services.parsers import parse_judgment, parse_legislation
from app.services.pdf import extract_pdf, extract_with_ocr
from app.services.text import classify_document

TERMINAL_STATES = {
    IngestionState.COMPLETED,
    IngestionState.FAILED_RETRYABLE,
    IngestionState.FAILED_TERMINAL,
    IngestionState.SKIPPED_DUPLICATE,
    IngestionState.SKIPPED_UNSUPPORTED,
    IngestionState.CANCELLED,
}


async def _transition(
    session, item: IngestionItem, state: IngestionState, details: dict | None = None
) -> None:
    item.state = state
    event = StageEvent(
        item_id=item.id, stage=state, details=details or {}, completed_at=datetime.now(UTC)
    )
    session.add(event)
    await session.flush()


async def _error(
    session,
    item: IngestionItem,
    state: IngestionState,
    exc: Exception,
    retryable: bool,
) -> None:
    item.last_error = str(exc)[-4000:]
    item.state = IngestionState.FAILED_RETRYABLE if retryable else IngestionState.FAILED_TERMINAL
    session.add(
        IngestionError(
            item_id=item.id,
            stage=state,
            error_type=type(exc).__name__,
            message=str(exc)[-4000:],
            retryable=retryable,
            details={},
        )
    )
    await session.flush()


async def _persist_parsed_structure(
    session, document: Document, parsed, document_type: DocumentType
) -> None:
    if document_type in {DocumentType.BARE_ACT, DocumentType.RULE, DocumentType.REGULATION}:
        act = Act(
            document_id=document.id, name=parsed.title, year=parsed.year, short_title=parsed.title
        )
        session.add(act)
        await session.flush()
        part_map: dict[str, LegalPart] = {}
        for part in parsed.parts:
            row = LegalPart(
                act_id=act.id,
                label=part.label,
                title=part.title,
                page_start=part.page_start,
                page_end=part.page_end,
            )
            session.add(row)
            part_map[part.label] = row
        await session.flush()
        chapter_map: dict[str, LegalChapter] = {}
        for chapter in parsed.chapters:
            part = part_map.get(chapter.part_label or "")
            if not part:
                continue
            row = LegalChapter(
                part_id=part.id,
                label=chapter.label,
                title=chapter.title,
                page_start=chapter.page_start,
                page_end=chapter.page_end,
            )
            session.add(row)
            chapter_map[chapter.label] = row
        await session.flush()
        for section in parsed.sections:
            part = next(
                (p for p in part_map.values() if p.page_start <= section.page_start <= p.page_end),
                None,
            )
            chapter = next(
                (
                    c
                    for c in chapter_map.values()
                    if c.page_start <= section.page_start <= c.page_end
                ),
                None,
            )
            session.add(
                LegalSection(
                    act_id=act.id,
                    part_id=part.id if part else None,
                    chapter_id=chapter.id if chapter else None,
                    label=section.label,
                    heading=section.heading,
                    text=section.text,
                    page_start=section.page_start,
                    page_end=section.page_end,
                )
            )
    elif parsed.paragraphs:
        judgment = Judgment(
            document_id=document.id,
            case_title=parsed.title,
            court=parsed.court,
            case_number=parsed.case_number,
            decision_date=parsed.decision_date,
            coram_text=parsed.coram_text,
        )
        session.add(judgment)
        await session.flush()
        for paragraph in parsed.paragraphs:
            session.add(
                JudgmentParagraph(
                    judgment_id=judgment.id,
                    official_number=paragraph.official_number,
                    internal_sequence=paragraph.internal_sequence,
                    text=paragraph.text,
                    page_start=paragraph.page_start,
                    page_end=paragraph.page_end,
                )
            )
    for reference in parsed.references:
        session.add(
            Reference(
                document_id=document.id,
                source_text=reference.source_text,
                reference_type=reference.reference_type,
                normalized_key=reference.normalized_key,
                resolution_status=reference.resolution_status,
                page_start=reference.page_start,
                page_end=reference.page_end,
            )
        )


async def _persist_embeddings(session, chunks: list[Chunk]) -> str:
    provider = get_embedding_provider()
    vectors = await asyncio.to_thread(provider.embed, [chunk.normalized_text for chunk in chunks])
    if len(vectors) != len(chunks):
        raise RuntimeError("embedding provider returned a count different from requested chunks")
    for chunk, vector in zip(chunks, vectors, strict=True):
        if len(vector) != provider.dimension:
            raise RuntimeError("embedding provider returned an incompatible vector dimension")
        session.add(
            Embedding(
                chunk_id=chunk.id,
                provider=provider.provider,
                model=provider.model,
                version=provider.version,
                dimension=provider.dimension,
                vector=vector,
            )
        )
    return f"{provider.provider}/{provider.model}/{provider.dimension}"


async def _process_item(session, item: IngestionItem) -> None:
    settings = get_settings()
    path = Path(item.path)
    item.attempts += 1
    await _transition(session, item, IngestionState.VALIDATING)
    valid, reason = validate_pdf(path, max_bytes=settings.max_pdf_bytes)
    if not valid:
        if reason == "source path does not exist":
            source = await session.scalar(select(Source).where(Source.path == str(path.resolve())))
            if source is not None:
                source.source_exists = False
                await session.execute(
                    Document.__table__.update()
                    .where(Document.source_id == source.id)
                    .values(missing_source=True)
                )
        if path.suffix.lower() != ".pdf":
            await _transition(
                session,
                item,
                IngestionState.SKIPPED_UNSUPPORTED,
                {"detail": reason},
            )
            return
        await _error(session, item, IngestionState.VALIDATING, ValueError(reason), retryable=False)
        return

    await _transition(session, item, IngestionState.EXTRACTING)
    try:
        binary_hash = await asyncio.to_thread(sha256_file, path)
        extracted = await asyncio.to_thread(extract_pdf, path, settings.max_pdf_bytes)
        if extracted.needs_ocr:
            await _transition(session, item, IngestionState.OCR)
            extracted = await asyncio.to_thread(extract_with_ocr, path)
    except (OSError, ValueError, RuntimeError) as exc:
        await _error(session, item, IngestionState.EXTRACTING, exc, retryable=True)
        return

    await _transition(session, item, IngestionState.NORMALIZING)
    normalized_all = "\n\n".join(page.normalized_text for page in extracted.pages)
    normalized_hash = sha256_text(normalized_all)
    existing = await session.scalar(select(Document).where(Document.sha256 == binary_hash))
    if existing:
        item.document_id = existing.id
        await _transition(
            session,
            item,
            IngestionState.SKIPPED_DUPLICATE,
            {"kind": DuplicateKind.EXACT_DUPLICATE.value},
        )
        return
    content_duplicate = await session.scalar(
        select(Document).where(Document.normalized_text_hash == normalized_hash)
    )

    source = await session.scalar(select(Source).where(Source.path == str(path.resolve())))
    if source is None:
        source = Source(path=str(path.resolve()), storage_mode="REFERENCE", source_exists=True)
        session.add(source)
        await session.flush()
    else:
        source.source_exists = True
        source.last_seen_at = datetime.now(UTC)

    await _transition(session, item, IngestionState.CLASSIFYING)
    classification = classify_document(normalized_all, path.name)
    document = Document(
        source_id=source.id,
        filename=path.name,
        sha256=binary_hash,
        normalized_text_hash=normalized_hash,
        byte_size=path.stat().st_size,
        page_count=extracted.page_count,
        document_type=classification.document_type,
        classification_method=classification.method,
        classification_confidence=classification.confidence,
        title=None,
        metadata_json={"classification_signals": classification.signals},
    )
    session.add(document)
    await session.flush()
    item.document_id = document.id

    if content_duplicate:
        session.add(
            DuplicateRecord(
                document_id=document.id,
                related_document_id=content_duplicate.id,
                kind=DuplicateKind.CONTENT_DUPLICATE,
                evidence={"normalized_text_hash": normalized_hash},
            )
        )

    if settings.managed_archive_enabled:
        archive_target = settings.archive_root / binary_hash[:2] / f"{binary_hash}.pdf"
        archive_target.parent.mkdir(parents=True, exist_ok=True)
        if not archive_target.exists():
            await asyncio.to_thread(shutil.copy2, path, archive_target)
        source.storage_mode = "MANAGED_ARCHIVE"
        source.archived_path = str(archive_target)

    await _transition(session, item, IngestionState.STORING)
    page_entities: list[Page] = []
    offset = 0
    for page in extracted.pages:
        entity = Page(
            document_id=document.id,
            page_number=page.page_number,
            raw_text=page.raw_text,
            normalized_text=page.normalized_text,
            extraction_method=page.extraction_method,
            text_start_offset=offset,
            text_end_offset=offset + len(page.normalized_text),
            ocr_engine=page.ocr_engine,
            ocr_confidence=page.ocr_confidence,
            warnings=page.warnings,
        )
        page_entities.append(entity)
        session.add(entity)
        offset += len(page.normalized_text) + 2

    await _transition(session, item, IngestionState.PARSING)
    if classification.document_type in {
        DocumentType.BARE_ACT,
        DocumentType.RULE,
        DocumentType.REGULATION,
    }:
        parsed = parse_legislation(extracted.pages)
    elif classification.document_type in {
        DocumentType.SUPREME_COURT_JUDGMENT,
        DocumentType.HIGH_COURT_JUDGMENT,
        DocumentType.TRIBUNAL_DECISION,
        DocumentType.OTHER_LEGAL_DOCUMENT,
    }:
        parsed = parse_judgment(extracted.pages)
    else:
        parsed = parse_legislation(extracted.pages)
    document.title = parsed.title
    if parsed.year and not document.document_date:
        document.document_date = datetime(parsed.year, 1, 1).date()
    await session.flush()
    await _persist_parsed_structure(session, document, parsed, classification.document_type)

    await _transition(session, item, IngestionState.CHUNKING)
    drafts = build_chunks(
        classification.document_type, extracted.pages, parsed, str(path.resolve())
    )
    chunks: list[Chunk] = []
    for draft in drafts:
        chunk = Chunk(
            document_id=document.id,
            chunk_index=draft.chunk_index,
            text=draft.text,
            normalized_text=draft.normalized_text,
            document_type=draft.document_type,
            section_label=draft.section_label,
            paragraph_number=draft.paragraph_number,
            page_start=draft.page_start,
            page_end=draft.page_end,
            source_path=str(path.resolve()),
            char_count=draft.char_count,
            token_count=draft.token_count,
        )
        chunks.append(chunk)
        session.add(chunk)
    await session.flush()

    await _transition(session, item, IngestionState.INDEXING_TEXT, {"chunks": len(chunks)})
    await session.flush()
    await _transition(session, item, IngestionState.EMBEDDING)
    try:
        embedding_detail = await _persist_embeddings(session, chunks) if chunks else "no chunks"
        await _transition(
            session,
            item,
            IngestionState.EMBEDDING,
            {"status": "completed", "detail": embedding_detail},
        )
    except Exception as exc:
        session.add(
            IngestionError(
                item_id=item.id,
                stage=IngestionState.EMBEDDING,
                error_type=type(exc).__name__,
                message=str(exc)[-4000:],
                retryable=True,
                details={"canonical_ingestion_preserved": True},
            )
        )
        await _transition(
            session,
            item,
            IngestionState.EMBEDDING,
            {"status": "not completed", "error": type(exc).__name__},
        )
    await _transition(session, item, IngestionState.VALIDATING_RESULT)
    await _transition(
        session,
        item,
        IngestionState.COMPLETED,
        {"document_id": str(document.id), "pages": len(page_entities)},
    )


async def run_batch(batch_id: UUID) -> None:
    async with SessionFactory() as session:
        batch = await session.get(IngestionBatch, batch_id)
        if not batch:
            return
        batch.state = IngestionState.QUEUED
        batch.started_at = datetime.now(UTC)
        await session.commit()
        while True:
            batch = await session.get(IngestionBatch, batch_id)
            if not batch:
                return
            if batch.cancel_requested:
                batch.state = IngestionState.CANCELLED
                await session.execute(
                    IngestionItem.__table__.update()
                    .where(IngestionItem.batch_id == batch_id)
                    .where(~IngestionItem.state.in_(list(TERMINAL_STATES)))
                    .values(state=IngestionState.CANCELLED)
                )
                await session.commit()
                return
            if batch.pause_requested:
                batch.state = IngestionState.DISCOVERED
                await session.commit()
                return
            item = await session.scalar(
                select(IngestionItem)
                .where(IngestionItem.batch_id == batch_id)
                .where(~IngestionItem.state.in_(list(TERMINAL_STATES)))
                .order_by(IngestionItem.created_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if item is None:
                pending_id = await session.scalar(
                    select(IngestionItem.id)
                    .where(IngestionItem.batch_id == batch_id)
                    .where(~IngestionItem.state.in_(list(TERMINAL_STATES)))
                    .limit(1)
                )
                if pending_id is not None:
                    await session.rollback()
                    await asyncio.sleep(0.2)
                    continue
                failed_retryable = await session.scalar(
                    select(IngestionItem.id)
                    .where(IngestionItem.batch_id == batch_id)
                    .where(IngestionItem.state == IngestionState.FAILED_RETRYABLE)
                    .limit(1)
                )
                failed_terminal = await session.scalar(
                    select(IngestionItem.id)
                    .where(IngestionItem.batch_id == batch_id)
                    .where(IngestionItem.state == IngestionState.FAILED_TERMINAL)
                    .limit(1)
                )
                batch.state = (
                    IngestionState.FAILED_RETRYABLE
                    if failed_retryable is not None
                    else IngestionState.FAILED_TERMINAL
                    if failed_terminal is not None
                    else IngestionState.COMPLETED
                )
                batch.completed_at = datetime.now(UTC)
                await session.commit()
                return
            item.locked_at = datetime.now(UTC)
            try:
                await _process_item(session, item)
            except Exception as exc:
                await session.rollback()
                item = await session.get(IngestionItem, item.id)
                if item is None:
                    return
                await _error(
                    session,
                    item,
                    IngestionState.STORING,
                    exc,
                    retryable=not isinstance(exc, IntegrityError),
                )
            item.locked_at = None
            await session.commit()


async def resume_incomplete_batches() -> None:
    await recover_stale_items()
    async with SessionFactory() as session:
        batch_ids = (
            await session.scalars(
                select(IngestionBatch.id).where(~IngestionBatch.state.in_(list(TERMINAL_STATES)))
            )
        ).all()
    await asyncio.gather(*(run_batch(batch_id) for batch_id in batch_ids))


async def recover_stale_items() -> int:
    recovered = 0
    async with SessionFactory() as session:
        items = (
            await session.scalars(
                select(IngestionItem).where(IngestionItem.state.not_in(list(TERMINAL_STATES)))
            )
        ).all()
        for item in items:
            if item.locked_at is not None:
                item.locked_at = None
                recovered += 1
        await session.commit()
    return recovered
