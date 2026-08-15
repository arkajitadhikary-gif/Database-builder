import asyncio
import selectors
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DATABASE_URL = 'postgresql+psycopg://judicore:judicore@127.0.0.1:5432/judicore'

async def main():
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        mod = await conn.scalar(text("SELECT atttypmod FROM pg_attribute WHERE attrelid = 'embeddings'::regclass AND attname = 'vector' AND NOT attisdropped"))
        fmt = await conn.scalar(text("SELECT format_type(atttypid, atttypmod) FROM pg_attribute WHERE attrelid = 'embeddings'::regclass AND attname = 'vector' AND NOT attisdropped"))
        print(f"ATTTYPMOD: {mod}, FORMAT_TYPE: {fmt}")
        if fmt != 'vector(384)':
            print("Altering embeddings.vector to vector(384)...")
            await conn.execute(text("ALTER TABLE embeddings ALTER COLUMN vector TYPE vector(384)"))
            await conn.execute(text("UPDATE embeddings SET dimension = 384 WHERE dimension IS DISTINCT FROM 384"))
            mod_after = await conn.scalar(text("SELECT atttypmod FROM pg_attribute WHERE attrelid = 'embeddings'::regclass AND attname = 'vector' AND NOT attisdropped"))
            fmt_after = await conn.scalar(text("SELECT format_type(atttypid, atttypmod) FROM pg_attribute WHERE attrelid = 'embeddings'::regclass AND attname = 'vector' AND NOT attisdropped"))
            print(f"AFTER -> ATTTYPMOD: {mod_after}, FORMAT_TYPE: {fmt_after}")
    await engine.dispose()

asyncio.run(main(), loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()))
