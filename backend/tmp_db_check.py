import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

async def main():
    engine = create_async_engine('postgresql+psycopg://judicore:judicore@127.0.0.1:5432/judicore')
    async with engine.connect() as conn:
        print('db=', await conn.scalar(text('SELECT current_database()')))
        print('schema=', await conn.scalar(text('SELECT current_schema()')))
        print('search_path=', await conn.scalar(text('SHOW search_path')))
        print('version_num=', await conn.scalar(text('SELECT version_num FROM alembic_version LIMIT 1')))
        print('dim=', await conn.scalar(text("SELECT atttypmod - 4 FROM pg_attribute WHERE attrelid = 'embeddings'::regclass AND attname = 'vector' AND NOT attisdropped")))
        print('type=', await conn.scalar(text("SELECT format_type(a.atttypid, a.atttypmod) FROM pg_attribute a WHERE a.attrelid = 'embeddings'::regclass AND a.attname = 'vector' AND NOT a.attisdropped")))
        print('count=', await conn.scalar(text('SELECT COUNT(*) FROM embeddings')))
    await engine.dispose()

asyncio.run(main())
