from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chunk, Document, Embedding, Source
from app.schemas.api import SearchHit, SearchRequest, SearchResponse
from app.services.embeddings import get_embedding_provider


async def _lexical(
    session: AsyncSession, payload: SearchRequest, limit: int
) -> list[tuple[Any, float]]:
    query = func.plainto_tsquery("simple", payload.query)
    rank = func.ts_rank_cd(Chunk.search_tsv, query)
    statement = (
        select(Chunk, Document, Source, rank.label("rank"))
        .join(Document, Chunk.document_id == Document.id)
        .join(Source, Document.source_id == Source.id)
        .where(Chunk.search_tsv.op("@@")(query))
        .order_by(desc("rank"))
        .limit(limit)
    )
    if payload.document_type:
        statement = statement.where(Document.document_type == payload.document_type)
    rows = (await session.execute(statement)).all()
    return rows


async def _semantic(
    session: AsyncSession, payload: SearchRequest, provider, limit: int
) -> list[tuple[Any, float]]:
    vector = provider.embed([payload.query])[0]
    distance = Embedding.vector.cosine_distance(vector)
    statement = (
        select(Chunk, Document, Source, distance.label("distance"))
        .join(Embedding, Embedding.chunk_id == Chunk.id)
        .join(Document, Chunk.document_id == Document.id)
        .join(Source, Document.source_id == Source.id)
        .where(Embedding.provider == provider.provider)
        .where(Embedding.model == provider.model)
        .order_by(distance)
        .limit(limit)
    )
    if payload.document_type:
        statement = statement.where(Document.document_type == payload.document_type)
    rows = (await session.execute(statement)).all()
    return rows


def _hit(
    chunk: Chunk,
    document: Document,
    source: Source,
    lexical_score: float | None,
    semantic_score: float | None,
    fused: float,
) -> SearchHit:
    return SearchHit(
        chunk_id=chunk.id,
        document_id=document.id,
        text=chunk.text,
        document_type=document.document_type.value,
        source_path=source.path,
        page_start=chunk.page_start,
        page_end=chunk.page_end,
        section_label=chunk.section_label,
        paragraph_number=chunk.paragraph_number,
        lexical_score=lexical_score,
        semantic_score=semantic_score,
        fused_score=fused,
    )


async def hybrid_search(session: AsyncSession, payload: SearchRequest) -> SearchResponse:
    candidate_limit = max(payload.limit, 50)
    lexical_rows = (
        await _lexical(session, payload, candidate_limit)
        if payload.mode in {"lexical", "hybrid"}
        else []
    )
    provider = None
    semantic_rows = []
    embedding_status = "NOT REQUESTED"
    if payload.mode in {"semantic", "hybrid"}:
        provider = get_embedding_provider()
        semantic_rows = await _semantic(session, payload, provider, candidate_limit)
        embedding_status = (
            f"READY:{provider.provider}/{provider.model}"
            if semantic_rows
            else f"NO_INDEXED_VECTORS:{provider.provider}/{provider.model}"
        )

    by_id: dict[str, dict[str, Any]] = defaultdict(dict)
    for rank, (chunk, document, source, score) in enumerate(lexical_rows, start=1):
        record = by_id[str(chunk.id)]
        record.update(chunk=chunk, document=document, source=source, lexical_score=float(score))
        record["lexical_rank"] = rank
    for rank, (chunk, document, source, distance) in enumerate(semantic_rows, start=1):
        record = by_id[str(chunk.id)]
        record.update(
            chunk=chunk,
            document=document,
            source=source,
            semantic_score=max(0.0, 1.0 - float(distance)),
        )
        record["semantic_rank"] = rank

    fused_records = []
    for record in by_id.values():
        fused_score = 0.0
        if "lexical_rank" in record:
            fused_score += 1.0 / (60.0 + record["lexical_rank"])
        if "semantic_rank" in record:
            fused_score += 1.0 / (60.0 + record["semantic_rank"])
        fused_records.append((fused_score, record))
    fused_records.sort(key=lambda item: item[0], reverse=True)
    hits = [
        _hit(
            record["chunk"],
            record["document"],
            record["source"],
            record.get("lexical_score"),
            record.get("semantic_score"),
            score,
        )
        for score, record in fused_records[: payload.limit]
    ]
    response_mode = payload.mode
    if payload.mode == "hybrid" and not semantic_rows:
        response_mode = "hybrid:semantic-unavailable"
    return SearchResponse(mode=response_mode, hits=hits, embedding_status=embedding_status)
