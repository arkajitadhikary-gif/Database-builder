import logging
from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)
EXPECTED_SCHEMA_REVISION = "0006_universal_tables"
engine = create_async_engine(
    str(settings.database_url),
    echo=False,
    pool_pre_ping=True,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    pool_timeout=settings.database_pool_timeout_seconds,
    pool_recycle=settings.database_pool_recycle_seconds,
    connect_args={"connect_timeout": settings.database_connect_timeout_seconds},
)

SessionFactory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionFactory() as session:
        yield session


async def check_database() -> tuple[bool, str]:
    try:
        async with engine.connect() as connection:
            await connection.exec_driver_sql("SELECT 1")
        return True, "connected"
    except Exception as exc:  # database diagnostics must not crash health endpoint
        return False, type(exc).__name__


async def check_database_schema() -> tuple[bool, str]:
    try:
        async with engine.connect() as connection:
            migration = await connection.scalar(
                text("SELECT version_num FROM alembic_version LIMIT 1")
            )
            vector = await connection.scalar(
                text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
            )
            dimension = await connection.scalar(
                text(
                    "SELECT atttypmod FROM pg_attribute "
                    "WHERE attrelid = 'embeddings'::regclass AND attname = 'vector' "
                    "AND NOT attisdropped"
                )
            )
            if migration is None:
                return False, "alembic_version is empty"
            if migration != EXPECTED_SCHEMA_REVISION:
                return False, f"schema revision {migration}; expected {EXPECTED_SCHEMA_REVISION}"
            if vector != 1:
                return False, f"pgvector extension missing at migration {migration}"
            logger.debug(
                "database schema check: migration=%s vector=%s dimension=%s expected=%s",
                migration,
                vector,
                dimension,
                settings.embedding_dimension,
            )
            if dimension != settings.embedding_dimension:
                return False, (
                    f"pgvector dimension {dimension}; expected {settings.embedding_dimension}; "
                    "controlled re-embedding migration required"
                )
            return True, f"migration={migration}; pgvector=ready; dimension={dimension}"
    except Exception as exc:  # schema diagnostics must not crash health endpoint
        return False, type(exc).__name__
