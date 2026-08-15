from __future__ import annotations

import asyncio
import shutil
from datetime import date, datetime
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.core.config import get_settings
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
)
from app.db.session import check_database_schema, get_session
from app.schemas.api import (
    ActStructureResponse,
    BatchCreateRequest,
    BatchItemResponse,
    BatchResponse,
    DatabaseOverviewResponse,
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
    return DatabaseOverviewResponse(tables=tables)


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


@api_router.post("/search", response_model=SearchResponse, tags=["search"])
async def search(
    payload: SearchRequest,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> SearchResponse:
    try:
        return await hybrid_search(session, payload)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
