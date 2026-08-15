import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings

EMBEDDING_ATTTYPMOD_SQL = (
    "SELECT atttypmod FROM pg_attribute "
    "WHERE attrelid = 'embeddings'::regclass "
    "AND attname = 'vector' AND NOT attisdropped"
)
EMBEDDING_FORMAT_SQL = (
    "SELECT format_type(atttypid, atttypmod) FROM pg_attribute "
    "WHERE attrelid = 'embeddings'::regclass "
    "AND attname = 'vector' AND NOT attisdropped"
)


async def main():
    engine = create_async_engine(str(get_settings().database_url))
    async with engine.begin() as conn:
        mod = await conn.scalar(text(EMBEDDING_ATTTYPMOD_SQL))
        fmt = await conn.scalar(text(EMBEDDING_FORMAT_SQL))
        print(f"ATTTYPMOD: {mod}, FORMAT_TYPE: {fmt}")
        if fmt != "vector(384)":
            print("Altering embeddings.vector to vector(384)...")
            await conn.execute(text("ALTER TABLE embeddings ALTER COLUMN vector TYPE vector(384)"))
            await conn.execute(
                text("UPDATE embeddings SET dimension = 384 WHERE dimension IS DISTINCT FROM 384")
            )
            mod_after = await conn.scalar(text(EMBEDDING_ATTTYPMOD_SQL))
            fmt_after = await conn.scalar(text(EMBEDDING_FORMAT_SQL))
            print(f"AFTER -> ATTTYPMOD: {mod_after}, FORMAT_TYPE: {fmt_after}")
    await engine.dispose()


asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)
