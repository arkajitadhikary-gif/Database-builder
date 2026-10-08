from __future__ import annotations

import asyncio
from dataclasses import dataclass

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chunk, Embedding
from app.services.embeddings import get_embedding_provider


@dataclass(frozen=True)
class EmbeddingBackfillResult:
    requested: int
    embedded: int
    provider: str
    model: str
    dimension: int


async def embed_missing_chunks(
    session: AsyncSession,
    limit: int = 100,
    document_id=None,
) -> EmbeddingBackfillResult:
    if limit < 1 or limit > 5000:
        raise ValueError("embedding backfill limit must be between 1 and 5000")
    provider = get_embedding_provider()
    compatible = exists(
        select(Embedding.id).where(
            Embedding.chunk_id == Chunk.id,
            Embedding.provider == provider.provider,
            Embedding.model == provider.model,
            Embedding.dimension == provider.dimension,
        )
    )
    query = (
        select(Chunk)
        .where(~compatible)
        .order_by(Chunk.created_at)
        .with_for_update(skip_locked=True)
        .limit(limit)
    )
    if document_id is not None:
        query = query.where(Chunk.document_id == document_id)
    chunks = list((await session.scalars(query)).all())
    if not chunks:
        return EmbeddingBackfillResult(0, 0, provider.provider, provider.model, provider.dimension)
    vectors = await asyncio.to_thread(provider.embed, [chunk.normalized_text for chunk in chunks])
    if len(vectors) != len(chunks):
        raise RuntimeError("embedding provider returned an invalid vector count")
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
    await session.commit()
    return EmbeddingBackfillResult(
        len(chunks), len(chunks), provider.provider, provider.model, provider.dimension
    )
