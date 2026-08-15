from __future__ import annotations

import asyncio
import json
import shutil
from datetime import date, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.core.config import get_settings
from app.db.base import Base
from app.db.models import (
    Act,
    Chunk,
    Document,
    Embedding,
    IngestionBatch,
    IngestionItem,
    IngestionState,
    Judgment,
    Page,
    Reference,
    VerificationFinding,
    VerificationRun,
)
from app.db.session import check_database_schema, get_session
from app.schemas.api import (
    ActStructureResponse,
    AiCapabilitiesResponse,
    BatchCreateRequest,
    BatchItemResponse,
    BatchResponse,
    DatabaseOverviewResponse,
    DatabaseRecordResponse,
    DatabaseTablePageResponse,
    DatabaseTableResponse,
    DocumentResponse,
    DocumentStructureResponse,
    EmbeddingBackfillRequest,
    EmbeddingBackfillResponse,
    HealthComponent,
    JudgmentParagraphResponse,
    JudgmentStructureResponse,
    LegalSectionResponse,
    PageResponse,
    ReferenceResponse,
    SearchRequest,
    SearchResponse,
    SetupResponse,
    VerificationFindingResponse,
    VerificationReviewResponse,
)
from app.services.discovery import discover_paths
from app.services.embedding_jobs import embed_missing_chunks
from app.services.embeddings import check_embedding_provider
from app.services.pdf import ocr_available, resolve_executable
from app.services.retrieval import hybrid_search
from app.workers.ingestion import run_batch

api_router = APIRouter()
settings = get_settings()
_background_tasks: dict[UUID, asyncio.Task[None]] = {}

DOMAIN_TABLE_LABELS = {
    "sources": "Sources",
    "acts": "Acts",
    "legal_parts": "Legal parts",
    "legal_chapters": "Legal chapters",
    "legal_sections": "Legal sections",
    "legal_nodes": "Legal nodes",
    "judgments": "Judgments",
    "judges": "Judges",
    "judgment_judges": "Judgment judges",
    "parties": "Parties",
    "judgment_paragraphs": "Judgment paragraphs",
    "stage_events": "Stage events",
    "ingestion_errors": "Ingestion errors",
    "duplicates": "Duplicates",
    "document_versions": "Document versions",
}


def _launch_batch(batch_id: UUID) -> None:
    existing = _background_tasks.get(batch_id)
    if existing is not None and not existing.done():
        return
    task = asyncio.create_task(run_batch(batch_id))
    _background_tasks[batch_id] = task

    def _cleanup(completed: asyncio.Task[None]) -> None:
        if _background_tasks.get(batch_id) is completed:
            _background_tasks.pop(batch_id, None)
        if not completed.cancelled() and completed.exception() is not None:
            completed.exception()

    task.add_done_callback(_cleanup)


async def _create_batch_from_discovery(
    session: AsyncSession,
    requested_paths: list[str],
    discovery_paths: list[str],
    recursive: bool,
) -> BatchResponse:
    try:
        paths = discover_paths(
            discovery_paths,
            recursive=recursive,
            max_files=settings.max_discovered_files,
        )
    except ValueError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    if not paths:
        raise HTTPException(
            status_code=400,
            detail="no files were discovered from the supplied paths",
        )
    batch = IngestionBatch(
        state=IngestionState.DISCOVERED,
        requested_paths=requested_paths,
        recursive=recursive,
    )
    batch.items = [IngestionItem(path=str(path), state=IngestionState.DISCOVERED) for path in paths]
    session.add(batch)
    await session.commit()
    await session.refresh(batch, attribute_names=["items"])
    _launch_batch(batch.id)
    return BatchResponse.from_orm(batch)


async def _store_uploaded_files(files: list[UploadFile]) -> tuple[Path, list[str], list[str]]:
    if not files:
        raise HTTPException(status_code=400, detail="select at least one file")
    if len(files) > settings.max_discovered_files:
        raise HTTPException(status_code=413, detail="upload contains too many files")

    upload_root = settings.reference_root / ".web-uploads" / uuid4().hex
    upload_root.mkdir(parents=True, exist_ok=False)
    stored_paths: list[str] = []
    requested_names: list[str] = []
    try:
        for index, upload in enumerate(files, start=1):
            original_name = (upload.filename or f"upload-{index}.bin").replace("\\", "/")
            safe_name = Path(original_name).name or f"upload-{index}.bin"
            destination = upload_root / f"{index:04d}-{safe_name}"
            size = 0
            try:
                with destination.open("wb") as handle:
                    while chunk := await upload.read(1024 * 1024):
                        size += len(chunk)
                        if size > settings.max_pdf_bytes:
                            raise HTTPException(
                                status_code=413,
                                detail=(
                                    "file exceeds configured size limit of "
                                    f"{settings.max_pdf_bytes} bytes"
                                ),
                            )
                        handle.write(chunk)
            finally:
                await upload.close()
            stored_paths.append(str(destination))
            requested_names.append(safe_name)
    except Exception:
        shutil.rmtree(upload_root, ignore_errors=True)
        raise
    return upload_root, stored_paths, requested_names


def _database_value(value: object) -> object:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "value"):
        return value.value
    return value


def _database_row(**values: object) -> dict[str, object]:
    return {key: _database_value(value) for key, value in values.items()}


async def _table_count(session: AsyncSession, model: type) -> int:
    return int(await session.scalar(select(func.count()).select_from(model)) or 0)


@api_router.get(
    "/database/overview", response_model=DatabaseOverviewResponse, tags=["database"]
)
async def database_overview(
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> DatabaseOverviewResponse:
    """Return a bounded, read-only snapshot for the visual database browser."""
    documents = (
        await session.scalars(
            select(Document)
            .options(joinedload(Document.source))
            .order_by(desc(Document.created_at))
            .limit(50)
        )
    ).all()
    pages = (
        await session.scalars(
            select(Page)
            .options(joinedload(Page.document))
            .order_by(desc(Page.created_at))
            .limit(50)
        )
    ).all()
    chunks = (
        await session.scalars(select(Chunk).order_by(desc(Chunk.created_at)).limit(50))
    ).all()
    references = (
        await session.scalars(select(Reference).order_by(desc(Reference.created_at)).limit(50))
    ).all()
    batches = (
        await session.scalars(
            select(IngestionBatch)
            .options(selectinload(IngestionBatch.items))
            .order_by(desc(IngestionBatch.created_at))
            .limit(50)
        )
    ).all()
    items = (
        await session.scalars(
            select(IngestionItem).order_by(desc(IngestionItem.created_at)).limit(50)
        )
    ).all()
    embeddings = (
        await session.scalars(select(Embedding).order_by(desc(Embedding.created_at)).limit(50))
    ).all()

    tables = [
        DatabaseTableResponse(
            key="documents",
            label="Documents",
            count=await _table_count(session, Document),
            columns=["id", "filename", "document_type", "page_count", "byte_size", "created_at"],
            rows=[
                _database_row(
                    id=row.id,
                    filename=row.filename,
                    document_type=row.document_type,
                    page_count=row.page_count,
                    byte_size=row.byte_size,
                    created_at=row.created_at,
                )
                for row in documents
            ],
        ),
        DatabaseTableResponse(
            key="pages",
            label="Pages",
            count=await _table_count(session, Page),
            columns=["id", "document", "page_number", "extraction_method", "text_preview"],
            rows=[
                _database_row(
                    id=row.id,
                    document=row.document.filename,
                    page_number=row.page_number,
                    extraction_method=row.extraction_method,
                    text_preview=row.normalized_text[:240],
                )
                for row in pages
            ],
        ),
        DatabaseTableResponse(
            key="chunks",
            label="Chunks",
            count=await _table_count(session, Chunk),
            columns=["id", "document_id", "chunk_index", "page_start", "page_end", "text_preview"],
            rows=[
                _database_row(
                    id=row.id,
                    document_id=row.document_id,
                    chunk_index=row.chunk_index,
                    page_start=row.page_start,
                    page_end=row.page_end,
                    text_preview=row.text[:240],
                )
                for row in chunks
            ],
        ),
        DatabaseTableResponse(
            key="references",
            label="References",
            count=await _table_count(session, Reference),
            columns=[
                "id",
                "document_id",
                "reference_type",
                "resolution_status",
                "page_start",
                "page_end",
            ],
            rows=[
                _database_row(
                    id=row.id,
                    document_id=row.document_id,
                    reference_type=row.reference_type,
                    resolution_status=row.resolution_status,
                    page_start=row.page_start,
                    page_end=row.page_end,
                )
                for row in references
            ],
        ),
        DatabaseTableResponse(
            key="ingestion_batches",
            label="Ingestion batches",
            count=await _table_count(session, IngestionBatch),
            columns=["id", "state", "items", "completed", "failed", "created_at"],
            rows=[
                _database_row(
                    id=row.id,
                    state=row.state,
                    items=len(row.items),
                    completed=sum(item.state == IngestionState.COMPLETED for item in row.items),
                    failed=sum(item.state.value.startswith("FAILED") for item in row.items),
                    created_at=row.created_at,
                )
                for row in batches
            ],
        ),
        DatabaseTableResponse(
            key="ingestion_items",
            label="Ingestion items",
            count=await _table_count(session, IngestionItem),
            columns=["id", "batch_id", "state", "attempts", "path", "last_error"],
            rows=[
                _database_row(
                    id=row.id,
                    batch_id=row.batch_id,
                    state=row.state,
                    attempts=row.attempts,
                    path=row.path,
                    last_error=row.last_error,
                )
                for row in items
            ],
        ),
        DatabaseTableResponse(
            key="embeddings",
            label="Embeddings",
            count=await _table_count(session, Embedding),
            columns=["id", "chunk_id", "provider", "model", "dimension", "created_at"],
            rows=[
                _database_row(
                    id=row.id,
                    chunk_id=row.chunk_id,
                    provider=row.provider,
                    model=row.model,
                    dimension=row.dimension,
                    created_at=row.created_at,
                )
                for row in embeddings
            ],
        ),
    ]
    for key, label in DOMAIN_TABLE_LABELS.items():
        table = Base.metadata.tables[key]
        tables.append(
            DatabaseTableResponse(
                key=key,
                label=label,
                count=await _table_count(session, table),
                columns=[column.name for column in table.columns if column.name != "vector"],
                rows=[],
            )
        )
    return DatabaseOverviewResponse(tables=tables)


@api_router.get(
    "/database/tables/{table_key}",
    response_model=DatabaseTablePageResponse,
    tags=["database"],
)
async def database_table(
    table_key: str,
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> DatabaseTablePageResponse:
    """Read a page of an allow-listed table for the spreadsheet-style viewer."""
    labels = {
        "documents": "Documents",
        "pages": "Pages",
        "chunks": "Chunks",
        "references": "References",
        "ingestion_batches": "Ingestion batches",
        "ingestion_items": "Ingestion items",
        "embeddings": "Embeddings metadata",
        **DOMAIN_TABLE_LABELS,
    }
    models = {
        "documents": Document,
        "pages": Page,
        "chunks": Chunk,
        "references": Reference,
        "ingestion_batches": IngestionBatch,
        "ingestion_items": IngestionItem,
        "embeddings": Embedding,
    }
    if table_key not in labels:
        raise HTTPException(
            status_code=404, detail="table is not available in the read-only viewer"
        )
    model = models.get(table_key)
    if model is None:
        table = Base.metadata.tables[table_key]
        count = await _table_count(session, table)
        columns = [column.name for column in table.columns if column.name != "vector"]
        selected_columns = [table.c[column] for column in columns]
        result = await session.execute(
            select(*selected_columns).offset(offset).limit(limit)
        )
        values = [_database_row(**dict(row)) for row in result.mappings().all()]
        return DatabaseTablePageResponse(
            key=table_key,
            label=labels[table_key],
            count=count,
            offset=offset,
            limit=limit,
            columns=columns,
            rows=values,
        )
    count = await _table_count(session, model)

    if table_key == "documents":
        columns = [
            "id", "source_id", "filename", "sha256", "normalized_text_hash", "byte_size",
            "page_count", "document_type", "classification_method", "classification_confidence",
            "title", "document_date", "missing_source", "created_at", "updated_at",
        ]
        rows = (
            await session.scalars(
                select(Document).order_by(Document.created_at).offset(offset).limit(limit)
            )
        ).all()
        values = [
            _database_row(
                id=row.id, source_id=row.source_id, filename=row.filename, sha256=row.sha256,
                normalized_text_hash=row.normalized_text_hash, byte_size=row.byte_size,
                page_count=row.page_count, document_type=row.document_type,
                classification_method=row.classification_method,
                classification_confidence=row.classification_confidence, title=row.title,
                document_date=row.document_date, missing_source=row.missing_source,
                created_at=row.created_at, updated_at=row.updated_at,
            )
            for row in rows
        ]
    elif table_key == "pages":
        columns = [
            "id", "document_id", "page_number", "raw_text", "normalized_text",
            "extraction_method", "text_start_offset", "text_end_offset", "ocr_engine",
            "ocr_confidence", "warnings", "created_at", "updated_at",
        ]
        rows = (
            await session.scalars(
                select(Page).order_by(Page.created_at).offset(offset).limit(limit)
            )
        ).all()
        values = [
            _database_row(
                id=row.id, document_id=row.document_id, page_number=row.page_number,
                raw_text=row.raw_text, normalized_text=row.normalized_text,
                extraction_method=row.extraction_method, text_start_offset=row.text_start_offset,
                text_end_offset=row.text_end_offset, ocr_engine=row.ocr_engine,
                ocr_confidence=row.ocr_confidence, warnings=row.warnings,
                created_at=row.created_at, updated_at=row.updated_at,
            )
            for row in rows
        ]
    elif table_key == "chunks":
        columns = [
            "id", "document_id", "chunk_index", "text", "normalized_text", "document_type",
            "section_label", "paragraph_number", "page_start", "page_end", "source_path",
            "char_count", "token_count", "created_at", "updated_at",
        ]
        rows = (
            await session.scalars(
                select(Chunk).order_by(Chunk.created_at).offset(offset).limit(limit)
            )
        ).all()
        values = [
            _database_row(
                id=row.id, document_id=row.document_id, chunk_index=row.chunk_index,
                text=row.text, normalized_text=row.normalized_text, document_type=row.document_type,
                section_label=row.section_label, paragraph_number=row.paragraph_number,
                page_start=row.page_start, page_end=row.page_end, source_path=row.source_path,
                char_count=row.char_count, token_count=row.token_count,
                created_at=row.created_at, updated_at=row.updated_at,
            )
            for row in rows
        ]
    elif table_key == "references":
        columns = [
            "id", "document_id", "source_text", "reference_type", "normalized_key",
            "resolution_status", "target_document_id", "page_start", "page_end",
            "created_at", "updated_at",
        ]
        rows = (
            await session.scalars(
                select(Reference).order_by(Reference.created_at).offset(offset).limit(limit)
            )
        ).all()
        values = [
            _database_row(
                id=row.id, document_id=row.document_id, source_text=row.source_text,
                reference_type=row.reference_type, normalized_key=row.normalized_key,
                resolution_status=row.resolution_status, target_document_id=row.target_document_id,
                page_start=row.page_start, page_end=row.page_end,
                created_at=row.created_at, updated_at=row.updated_at,
            )
            for row in rows
        ]
    elif table_key == "ingestion_batches":
        columns = [
            "id", "state", "requested_paths", "recursive", "pause_requested",
            "cancel_requested", "started_at", "completed_at", "created_at", "updated_at",
        ]
        rows = (
            await session.scalars(
                select(IngestionBatch).order_by(IngestionBatch.created_at).offset(offset).limit(limit)
            )
        ).all()
        values = [
            _database_row(
                id=row.id, state=row.state, requested_paths=row.requested_paths,
                recursive=row.recursive, pause_requested=row.pause_requested,
                cancel_requested=row.cancel_requested, started_at=row.started_at,
                completed_at=row.completed_at, created_at=row.created_at, updated_at=row.updated_at,
            )
            for row in rows
        ]
    elif table_key == "ingestion_items":
        columns = [
            "id", "batch_id", "path", "state", "attempts", "locked_at", "last_error",
            "document_id", "created_at", "updated_at",
        ]
        rows = (
            await session.scalars(
                select(IngestionItem).order_by(IngestionItem.created_at).offset(offset).limit(limit)
            )
        ).all()
        values = [
            _database_row(
                id=row.id, batch_id=row.batch_id, path=row.path, state=row.state,
                attempts=row.attempts, locked_at=row.locked_at, last_error=row.last_error,
                document_id=row.document_id, created_at=row.created_at, updated_at=row.updated_at,
            )
            for row in rows
        ]
    else:
        columns = [
            "id",
            "chunk_id",
            "provider",
            "model",
            "version",
            "dimension",
            "created_at",
            "updated_at",
        ]
        rows = (
            await session.scalars(
                select(Embedding).order_by(Embedding.created_at).offset(offset).limit(limit)
            )
        ).all()
        values = [
            _database_row(
                id=row.id, chunk_id=row.chunk_id, provider=row.provider, model=row.model,
                version=row.version, dimension=row.dimension, created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        ]

    return DatabaseTablePageResponse(
        key=table_key,
        label=labels[table_key],
        count=count,
        offset=offset,
        limit=limit,
        columns=columns,
        rows=values,
    )


@api_router.get(
    "/database/tables/{table_key}/{row_id}",
    response_model=DatabaseRecordResponse,
    tags=["database"],
)
async def database_record(
    table_key: str,
    row_id: UUID,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> DatabaseRecordResponse:
    model_map = {
        "documents": Document,
        "pages": Page,
        "chunks": Chunk,
        "references": Reference,
        "ingestion_batches": IngestionBatch,
        "ingestion_items": IngestionItem,
        "embeddings": Embedding,
    }
    labels = {
        "documents": "Documents",
        "pages": "Pages",
        "chunks": "Chunks",
        "references": "References",
        "ingestion_batches": "Ingestion batches",
        "ingestion_items": "Ingestion items",
        "embeddings": "Embeddings metadata",
    }
    model = model_map.get(table_key)
    if model is None:
        table = Base.metadata.tables.get(table_key)
        if table is None or "id" not in table.c:
            raise HTTPException(
                status_code=404,
                detail="row detail is not available for this table",
            )
        result = await session.execute(
            select(table).where(table.c.id == row_id)
        )
        mapping = result.mappings().first()
        if mapping is None:
            raise HTTPException(status_code=404, detail="row not found")
        columns = [column.name for column in table.columns if column.name != "vector"]
        row_values = _database_row(
            **{column: mapping[column] for column in columns}
        )
        generic_provenance = {
            "table": table_key,
            "row_id": str(row_id),
            **{
                key: row_values[key]
                for key in ("document_id", "page_start", "page_end", "item_id", "act_id")
                if key in row_values
            },
        }
        return DatabaseRecordResponse(
            key=table_key,
            label=DOMAIN_TABLE_LABELS[table_key],
            row_id=row_id,
            columns=columns,
            row=row_values,
            provenance=generic_provenance,
        )
    row = await session.get(model, row_id)
    if row is None:
        raise HTTPException(status_code=404, detail="row not found")
    table_page = await database_table(table_key, 1, 0, session)
    row_values = {
        column: _database_value(getattr(row, column, None)) for column in table_page.columns
    }
    provenance: dict[str, object] = {"table": table_key, "row_id": str(row_id)}
    if table_key == "documents":
        source = await session.scalar(
            select(Document).options(joinedload(Document.source)).where(Document.id == row_id)
        )
        provenance.update(
            {
                "document_id": str(row_id),
                "filename": source.filename,
                "source_path": source.source.path,
            }
        )
    elif table_key == "pages":
        page = await session.scalar(
            select(Page)
            .options(joinedload(Page.document).joinedload(Document.source))
            .where(Page.id == row_id)
        )
        provenance.update(
            {
                "document_id": str(page.document_id),
                "page_number": page.page_number,
                "filename": page.document.filename,
                "source_path": page.document.source.path,
            }
        )
    elif table_key == "chunks":
        chunk = await session.scalar(select(Chunk).where(Chunk.id == row_id))
        document = await session.scalar(
            select(Document)
            .options(joinedload(Document.source))
            .where(Document.id == chunk.document_id)
        )
        provenance.update(
            {
                "document_id": str(chunk.document_id),
                "page_start": chunk.page_start,
                "page_end": chunk.page_end,
                "filename": document.filename,
                "source_path": document.source.path,
            }
        )
    elif table_key == "references":
        reference = await session.scalar(select(Reference).where(Reference.id == row_id))
        provenance.update(
            {
                "document_id": str(reference.document_id),
                "page_start": reference.page_start,
                "page_end": reference.page_end,
            }
        )
    elif table_key == "ingestion_items":
        provenance.update(
            {
                "batch_id": str(row.batch_id),
                "document_id": str(row.document_id) if row.document_id else None,
            }
        )
    elif table_key == "embeddings":
        chunk = await session.scalar(select(Chunk).where(Chunk.id == row.chunk_id))
        provenance.update(
            {
                "chunk_id": str(row.chunk_id),
                "document_id": str(chunk.document_id) if chunk else None,
            }
        )
    return DatabaseRecordResponse(
        key=table_key,
        label=labels[table_key],
        row_id=row_id,
        columns=table_page.columns,
        row=row_values,
        provenance=provenance,
    )


@api_router.get("/setup", response_model=SetupResponse, tags=["setup"])
async def setup_status() -> SetupResponse:
    postgres_ok = False
    try:
        from app.db.session import check_database

        postgres_ok, database_detail = await check_database()
    except Exception as exc:
        database_detail = type(exc).__name__
    schema_ok, schema_detail = (
        await check_database_schema() if postgres_ok else (False, "database unavailable")
    )
    tesseract_path = resolve_executable("tesseract")
    ocrmypdf_path = resolve_executable("ocrmypdf")
    ocr_ok, ocr_detail = ocr_available()
    embedding_ok, embedding_detail = await asyncio.to_thread(check_embedding_provider)
    return SetupResponse(
        components=[
            HealthComponent(name="Backend", status="READY", detail="FastAPI is running"),
            HealthComponent(
                name="PostgreSQL",
                status="READY" if postgres_ok else "ERROR",
                detail=database_detail,
            ),
            HealthComponent(
                name="Alembic + pgvector schema",
                status="READY" if schema_ok else "NOT CONFIGURED",
                detail=schema_detail,
            ),
            HealthComponent(
                name="Tesseract",
                status="READY" if tesseract_path else "NOT CONFIGURED",
                detail=tesseract_path or "Executable not found on PATH",
            ),
            HealthComponent(
                name="OCRmyPDF",
                status="READY" if ocrmypdf_path else "NOT CONFIGURED",
                detail=ocrmypdf_path or "Executable not found on PATH",
            ),
            HealthComponent(
                name="OCR pipeline",
                status="READY" if ocr_ok else "NOT CONFIGURED",
                detail=ocr_detail,
            ),
            HealthComponent(
                name="Embedding subsystem",
                status="READY" if embedding_ok else "NOT CONFIGURED",
                detail=embedding_detail,
            ),
            HealthComponent(
                name="Reference storage",
                status="READY" if settings.reference_root.exists() else "ERROR",
                detail=str(settings.reference_root.resolve()),
            ),
        ]
    )


@api_router.post("/batches", response_model=BatchResponse, status_code=202, tags=["ingestion"])
async def create_batch(
    payload: BatchCreateRequest,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> BatchResponse:
    return await _create_batch_from_discovery(
        session,
        requested_paths=payload.paths,
        discovery_paths=payload.paths,
        recursive=payload.recursive,
    )


@api_router.post(
    "/batches/upload", response_model=BatchResponse, status_code=202, tags=["ingestion"]
)
async def create_uploaded_batch(
    files: list[UploadFile] = File(...),  # noqa: B008
    recursive: bool = Form(False),
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> BatchResponse:
    upload_root, stored_paths, requested_names = await _store_uploaded_files(files)
    try:
        return await _create_batch_from_discovery(
            session,
            requested_paths=requested_names,
            discovery_paths=stored_paths,
            recursive=recursive,
        )
    except Exception:
        shutil.rmtree(upload_root, ignore_errors=True)
        raise


@api_router.get("/batches", response_model=list[BatchResponse], tags=["ingestion"])
async def list_batches(
    limit: int = Query(default=50, ge=1, le=500),
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> list[BatchResponse]:
    rows = (
        await session.scalars(
            select(IngestionBatch)
            .options(selectinload(IngestionBatch.items))
            .order_by(desc(IngestionBatch.created_at))
            .limit(limit)
        )
    ).all()
    return [BatchResponse.from_orm(row) for row in rows]


@api_router.get("/batches/{batch_id}", response_model=BatchResponse, tags=["ingestion"])
async def get_batch(
    batch_id: UUID,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> BatchResponse:
    batch = await session.scalar(
        select(IngestionBatch)
        .options(selectinload(IngestionBatch.items))
        .where(IngestionBatch.id == batch_id)
    )
    if not batch:
        raise HTTPException(status_code=404, detail="batch not found")
    return BatchResponse.from_orm(batch)


@api_router.post("/batches/{batch_id}/pause", response_model=BatchResponse, tags=["ingestion"])
async def pause_batch(
    batch_id: UUID,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> BatchResponse:
    batch = await session.get(IngestionBatch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="batch not found")
    batch.pause_requested = True
    await session.commit()
    await session.refresh(batch, attribute_names=["items"])
    return BatchResponse.from_orm(batch)


@api_router.post("/batches/{batch_id}/resume", response_model=BatchResponse, tags=["ingestion"])
async def resume_batch(
    batch_id: UUID,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> BatchResponse:
    batch = await session.scalar(
        select(IngestionBatch)
        .options(selectinload(IngestionBatch.items))
        .where(IngestionBatch.id == batch_id)
    )
    if not batch:
        raise HTTPException(status_code=404, detail="batch not found")
    batch.pause_requested = False
    batch.cancel_requested = False
    await session.commit()
    _launch_batch(batch.id)
    await session.refresh(batch, attribute_names=["items"])
    return BatchResponse.from_orm(batch)


@api_router.post("/batches/{batch_id}/cancel", response_model=BatchResponse, tags=["ingestion"])
async def cancel_batch(
    batch_id: UUID,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> BatchResponse:
    batch = await session.scalar(
        select(IngestionBatch)
        .options(selectinload(IngestionBatch.items))
        .where(IngestionBatch.id == batch_id)
    )
    if not batch:
        raise HTTPException(status_code=404, detail="batch not found")
    batch.cancel_requested = True
    await session.commit()
    return BatchResponse.from_orm(batch)


@api_router.post("/batches/{batch_id}/retry", response_model=BatchResponse, tags=["ingestion"])
async def retry_batch(
    batch_id: UUID,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> BatchResponse:
    batch = await session.scalar(
        select(IngestionBatch)
        .options(selectinload(IngestionBatch.items))
        .where(IngestionBatch.id == batch_id)
    )
    if not batch:
        raise HTTPException(status_code=404, detail="batch not found")
    batch.cancel_requested = False
    batch.pause_requested = False
    batch.state = IngestionState.QUEUED
    for item in batch.items:
        if item.state in {
            IngestionState.FAILED_RETRYABLE,
            IngestionState.FAILED_TERMINAL,
        }:
            item.state = IngestionState.DISCOVERED
            item.last_error = None
    await session.commit()
    _launch_batch(batch.id)
    await session.refresh(batch, attribute_names=["items"])
    return BatchResponse.from_orm(batch)


@api_router.get(
    "/batches/{batch_id}/items", response_model=list[BatchItemResponse], tags=["ingestion"]
)
async def list_batch_items(
    batch_id: UUID,
    limit: int = Query(default=500, ge=1, le=5000),
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> list[BatchItemResponse]:
    batch_exists = await session.scalar(
        select(IngestionBatch.id).where(IngestionBatch.id == batch_id)
    )
    if batch_exists is None:
        raise HTTPException(status_code=404, detail="batch not found")
    items = (
        await session.scalars(
            select(IngestionItem)
            .where(IngestionItem.batch_id == batch_id)
            .order_by(IngestionItem.created_at)
            .limit(limit)
        )
    ).all()
    return [BatchItemResponse.from_orm(item) for item in items]


@api_router.post(
    "/embeddings/backfill",
    response_model=EmbeddingBackfillResponse,
    status_code=202,
    tags=["embeddings"],
)
async def backfill_embeddings(
    payload: EmbeddingBackfillRequest,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> EmbeddingBackfillResponse:
    try:
        result = await embed_missing_chunks(
            session,
            limit=payload.limit,
            document_id=payload.document_id,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return EmbeddingBackfillResponse(
        requested=result.requested,
        embedded=result.embedded,
        provider=result.provider,
        model=result.model,
        dimension=result.dimension,
    )


@api_router.get("/documents", response_model=list[DocumentResponse], tags=["documents"])
async def list_documents(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    document_type: str | None = None,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> list[DocumentResponse]:
    query = (
        select(Document)
        .options(joinedload(Document.source))
        .order_by(desc(Document.created_at))
        .offset(offset)
        .limit(limit)
    )
    if document_type:
        query = query.where(Document.document_type == document_type)
    rows = (await session.scalars(query)).all()
    return [DocumentResponse.from_orm(row) for row in rows]


@api_router.get("/documents/{document_id}", response_model=DocumentResponse, tags=["documents"])
async def get_document(
    document_id: UUID,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> DocumentResponse:
    document = await session.scalar(
        select(Document).options(joinedload(Document.source)).where(Document.id == document_id)
    )
    if not document:
        raise HTTPException(status_code=404, detail="document not found")
    return DocumentResponse.from_orm(document)


@api_router.get(
    "/documents/{document_id}/pages", response_model=list[PageResponse], tags=["documents"]
)
async def list_document_pages(
    document_id: UUID,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> list[PageResponse]:
    document_exists = await session.scalar(select(Document.id).where(Document.id == document_id))
    if document_exists is None:
        raise HTTPException(status_code=404, detail="document not found")
    pages = (
        await session.scalars(
            select(Page).where(Page.document_id == document_id).order_by(Page.page_number)
        )
    ).all()
    return [
        PageResponse(
            id=page.id,
            page_number=page.page_number,
            raw_text=page.raw_text,
            normalized_text=page.normalized_text,
            extraction_method=page.extraction_method.value,
            text_start_offset=page.text_start_offset,
            text_end_offset=page.text_end_offset,
            ocr_engine=page.ocr_engine,
            ocr_confidence=page.ocr_confidence,
            warnings=page.warnings,
        )
        for page in pages
    ]


@api_router.get(
    "/documents/{document_id}/structure",
    response_model=DocumentStructureResponse,
    tags=["documents"],
)
async def get_document_structure(
    document_id: UUID,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> DocumentStructureResponse:
    document_exists = await session.scalar(select(Document.id).where(Document.id == document_id))
    if document_exists is None:
        raise HTTPException(status_code=404, detail="document not found")
    act = await session.scalar(
        select(Act).options(selectinload(Act.sections)).where(Act.document_id == document_id)
    )
    judgment = await session.scalar(
        select(Judgment)
        .options(selectinload(Judgment.paragraphs))
        .where(Judgment.document_id == document_id)
    )
    references = (
        await session.scalars(
            select(Reference)
            .where(Reference.document_id == document_id)
            .order_by(Reference.page_start, Reference.created_at)
        )
    ).all()
    return DocumentStructureResponse(
        document_id=document_id,
        act=(
            ActStructureResponse(
                name=act.name,
                year=act.year,
                short_title=act.short_title,
                sections=[
                    LegalSectionResponse(
                        label=section.label,
                        heading=section.heading,
                        text=section.text,
                        page_start=section.page_start,
                        page_end=section.page_end,
                    )
                    for section in act.sections
                ],
            )
            if act
            else None
        ),
        judgment=(
            JudgmentStructureResponse(
                case_title=judgment.case_title,
                court=judgment.court,
                case_number=judgment.case_number,
                decision_date=judgment.decision_date,
                coram_text=judgment.coram_text,
                paragraphs=[
                    JudgmentParagraphResponse(
                        official_number=paragraph.official_number,
                        internal_sequence=paragraph.internal_sequence,
                        text=paragraph.text,
                        page_start=paragraph.page_start,
                        page_end=paragraph.page_end,
                    )
                    for paragraph in sorted(
                        judgment.paragraphs, key=lambda item: item.internal_sequence
                    )
                ],
            )
            if judgment
            else None
        ),
        references=[
            ReferenceResponse(
                id=reference.id,
                source_text=reference.source_text,
                reference_type=reference.reference_type,
                normalized_key=reference.normalized_key,
                resolution_status=reference.resolution_status.value,
                target_document_id=reference.target_document_id,
                page_start=reference.page_start,
                page_end=reference.page_end,
            )
            for reference in references
        ],
    )


def _require_ai_read_access(request: Request) -> None:
    configured = settings.ai_read_token
    if configured and request.headers.get("authorization") != f"Bearer {configured}":
        raise HTTPException(status_code=401, detail="AI read access token required")


@api_router.get(
    "/ai/capabilities",
    response_model=AiCapabilitiesResponse,
    tags=["ai-access"],
)
async def ai_capabilities(request: Request) -> AiCapabilitiesResponse:
    _require_ai_read_access(request)
    transfer_mode = (
        "local"
        if "localhost" in settings.ai_nim_base_url or "127.0.0.1" in settings.ai_nim_base_url
        else "hosted"
    )
    return AiCapabilitiesResponse(
        schema_version="0005_ai_verification",
        access_mode="read-only-openapi+mcp",
        read_only=True,
        tools=[
            "search_legal_documents",
            "get_document_context",
            "get_document_provenance",
            "list_table_rows",
            "get_table_row",
        ],
        verification_provider=settings.ai_verification_provider,
        verification_enabled=settings.ai_verification_enabled,
        transfer_mode=transfer_mode,
    )


@api_router.get("/ai/tables/{table_key}", tags=["ai-access"])
async def ai_table_rows(
    table_key: str,
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> DatabaseTablePageResponse:
    _require_ai_read_access(request)
    return await database_table(table_key, limit, offset, session)


@api_router.get("/ai/documents/{document_id}/context", tags=["ai-access"])
async def ai_document_context(
    document_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, object]:
    _require_ai_read_access(request)
    return {
        "document": (await get_document(document_id, session)).model_dump(mode="json"),
        "pages": [
            page.model_dump(mode="json")
            for page in await list_document_pages(document_id, session)
        ],
        "structure": (await get_document_structure(document_id, session)).model_dump(mode="json"),
    }


@api_router.get("/ai/tables/{table_key}/{row_id}", tags=["ai-access"])
async def ai_table_row(
    table_key: str,
    row_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> DatabaseRecordResponse:
    _require_ai_read_access(request)
    return await database_record(table_key, row_id, session)


@api_router.post("/ai/search", response_model=SearchResponse, tags=["ai-access"])
async def ai_search(
    payload: SearchRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> SearchResponse:
    _require_ai_read_access(request)
    return await search(payload, session)


MCP_TOOL_DEFINITIONS: list[dict[str, object]] = [
    {
        "name": "search_legal_documents",
        "description": "Search indexed legal text and return provenance-backed hits.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "mode": {"type": "string", "enum": ["lexical", "semantic", "hybrid"]},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_document_context",
        "description": "Read a document, its pages, parsed structure, and references.",
        "inputSchema": {
            "type": "object",
            "properties": {"document_id": {"type": "string", "format": "uuid"}},
            "required": ["document_id"],
        },
    },
    {
        "name": "list_table_rows",
        "description": "Read a bounded page from an allow-listed database table.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "table_key": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 500},
                "offset": {"type": "integer", "minimum": 0},
            },
            "required": ["table_key"],
        },
    },
    {
        "name": "get_table_row",
        "description": "Read one database row with its source/provenance metadata.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "table_key": {"type": "string"},
                "row_id": {"type": "string", "format": "uuid"},
            },
            "required": ["table_key", "row_id"],
        },
    },
]


def _mcp_result(request_id: object, value: object, *, is_error: bool = False) -> dict[str, object]:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "content": [{"type": "text", "text": text}],
            "structuredContent": value,
            "isError": is_error,
        },
    }


@api_router.post("/mcp", tags=["ai-access"])
async def mcp_endpoint(
    payload: dict[str, Any],
    request: Request,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, object]:
    """Small read-only MCP JSON-RPC adapter for local AI clients."""
    _require_ai_read_access(request)
    request_id = payload.get("id")
    method = payload.get("method")
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2025-06-18",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "judicore", "version": "0.1.0"},
            },
        }
    if method in {"notifications/initialized", "ping"}:
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": MCP_TOOL_DEFINITIONS}}
    if method != "tools/call":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32601, "message": f"unsupported MCP method: {method}"},
        }
    params = payload.get("params") or {}
    name = params.get("name")
    arguments = params.get("arguments") or {}
    try:
        if name == "search_legal_documents":
            value = (
                await search(SearchRequest.model_validate(arguments), session)
            ).model_dump(mode="json")
        elif name == "get_document_context":
            document_id = UUID(str(arguments["document_id"]))
            value = {
                "document": (await get_document(document_id, session)).model_dump(mode="json"),
                "pages": [
                    page.model_dump(mode="json")
                    for page in await list_document_pages(document_id, session)
                ],
                "structure": (
                    await get_document_structure(document_id, session)
                ).model_dump(mode="json"),
            }
        elif name == "list_table_rows":
            value = (
                await database_table(
                    str(arguments["table_key"]),
                    int(arguments.get("limit", 100)),
                    int(arguments.get("offset", 0)),
                    session,
                )
            ).model_dump(mode="json")
        elif name == "get_table_row":
            value = (
                await database_record(
                    str(arguments["table_key"]), UUID(str(arguments["row_id"])), session
                )
            ).model_dump(mode="json")
        else:
            return _mcp_result(request_id, f"unknown tool: {name}", is_error=True)
    except (KeyError, TypeError, ValueError, HTTPException) as exc:
        return _mcp_result(request_id, str(exc), is_error=True)
    return _mcp_result(request_id, value)


@api_router.get(
    "/verification/reviews",
    response_model=list[VerificationReviewResponse],
    tags=["verification"],
)
async def verification_reviews(
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> list[VerificationReviewResponse]:
    findings = (
        await session.scalars(
            select(VerificationFinding)
            .join(VerificationFinding.run)
            .options(
                joinedload(VerificationFinding.run)
                .joinedload(VerificationRun.item)
                .joinedload(IngestionItem.batch)
            )
            .where(VerificationFinding.decision == "OPEN")
            .order_by(desc(VerificationFinding.id))
            .limit(500)
        )
    ).all()
    grouped: dict[UUID, VerificationReviewResponse] = {}
    for finding in findings:
        item = finding.run.item
        review = grouped.setdefault(
            item.id,
            VerificationReviewResponse(
                item_id=item.id,
                batch_id=item.batch.id,
                path=item.path,
                state=item.state.value,
                findings=[],
            ),
        )
        review.findings.append(
            VerificationFindingResponse(
                id=finding.id,
                run_id=finding.run_id,
                severity=finding.severity,
                field_name=finding.field_name,
                message=finding.message,
                expected_value=finding.expected_value,
                observed_value=finding.observed_value,
                page_start=finding.page_start,
                page_end=finding.page_end,
                confidence=finding.confidence,
                evidence=finding.evidence,
                decision=finding.decision,
            )
        )
    return list(grouped.values())


@api_router.post("/search", response_model=SearchResponse, tags=["search"])
async def search(
    payload: SearchRequest,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> SearchResponse:
    try:
        return await hybrid_search(session, payload)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
