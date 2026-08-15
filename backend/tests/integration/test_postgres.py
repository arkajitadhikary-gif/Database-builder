from __future__ import annotations

import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DATABASE_URL = os.getenv("JUDICORE_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="Set JUDICORE_TEST_DATABASE_URL to an isolated PostgreSQL + pgvector database",
)


@pytest.mark.asyncio
async def test_postgres_persistence_fts_and_vector_roundtrip() -> None:
    assert DATABASE_URL is not None
    engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
    async with engine.begin() as connection:
        await connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await connection.execute(text("SELECT 1"))
    async with engine.connect() as connection:
        extension = await connection.scalar(
            text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
        )
        assert extension == 1
        table_exists = await connection.scalar(
            text("SELECT to_regclass('public.documents') IS NOT NULL")
        )
        assert table_exists is True
    await engine.dispose()


@pytest.mark.asyncio
async def test_postgres_transaction_rollback_isolation() -> None:
    assert DATABASE_URL is not None
    engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
    async with engine.begin() as connection:
        transaction = await connection.begin_nested()
        await connection.execute(text("SELECT 1"))
        await transaction.rollback()
    await engine.dispose()
