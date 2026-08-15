import asyncio
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DATABASE_URL = 'postgresql+psycopg://judicore:judicore@127.0.0.1:5432/judicore'
OUTPUT_PATH = Path(__file__).resolve().with_name('live_db_state.txt')

async def main() -> None:
    engine = create_async_engine(DATABASE_URL)
    lines: list[str] = []
    try:
        async with engine.begin() as conn:
            version = await conn.scalar(text('SELECT version_num FROM alembic_version LIMIT 1'))
            dim = await conn.scalar(text("SELECT (atttypmod - 4) FROM pg_attribute WHERE attrelid = 'embeddings'::regclass AND attname = 'vector' AND NOT attisdropped"))
            full_type = await conn.scalar(text("SELECT format_type(a.atttypid, a.atttypmod) FROM pg_attribute a WHERE a.attrelid = 'embeddings'::regclass AND a.attname = 'vector' AND NOT a.attisdropped"))
            try:
                await conn.execute(text("ALTER TABLE IF EXISTS embeddings ALTER COLUMN vector TYPE vector(384) USING vector::vector(384)"))
                await conn.execute(text("UPDATE embeddings SET dimension = 384 WHERE dimension IS DISTINCT FROM 384"))
                dim_after = await conn.scalar(text("SELECT (atttypmod - 4) FROM pg_attribute WHERE attrelid = 'embeddings'::regclass AND attname = 'vector' AND NOT attisdropped"))
                full_type_after = await conn.scalar(text("SELECT format_type(a.atttypid, a.atttypmod) FROM pg_attribute a WHERE a.attrelid = 'embeddings'::regclass AND a.attname = 'vector' AND NOT a.attisdropped"))
                lines.append(f'VERSION={version}')
                lines.append(f'DIM_BEFORE={dim}')
                lines.append(f'DIM_AFTER={dim_after}')
                lines.append(f'TYPE_BEFORE={full_type}')
                lines.append(f'TYPE_AFTER={full_type_after}')
            except Exception as exc:
                lines.append(f'REPAIR_ERROR={type(exc).__name__}: {exc}')
                raise
    finally:
        await engine.dispose()
    OUTPUT_PATH.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('\n'.join(lines))

asyncio.run(main())
