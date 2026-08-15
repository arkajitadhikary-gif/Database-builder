from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Judicore Legal Database Builder"
    environment: str = "development"
    host: str = "127.0.0.1"
    port: int = 8765
    database_url: PostgresDsn = Field(
        default="postgresql+psycopg://judicore:judicore@127.0.0.1:5432/judicore"
    )
    database_pool_size: int = 10
    database_max_overflow: int = 20
    database_pool_timeout_seconds: int = 30
    database_connect_timeout_seconds: int = 5
    database_pool_recycle_seconds: int = 1800
    reference_root: Path = Path("./storage/reference")
    archive_root: Path = Path("./storage/archive")
    managed_archive_enabled: bool = False
    max_extraction_workers: int = 2
    max_discovered_files: int = 100000
    max_pdf_bytes: int = 524288000
    max_ocr_workers: int = 1
    db_batch_size: int = 100
    embedding_batch_size: int = 32
    embedding_provider: str = "local"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dimension: int = 384
    embedding_device: str = "cpu"
    ocr_enabled: bool = True
    ocr_timeout_seconds: int = 180
    log_level: str = "INFO"
    session_token: str | None = Field(
        default=None,
        validation_alias=AliasChoices("SESSION_TOKEN", "JUDICORE_SESSION_TOKEN"),
    )

    @field_validator(
        "max_extraction_workers", "max_ocr_workers", "db_batch_size", "embedding_batch_size"
    )
    @classmethod
    def positive_integer(cls, value: int) -> int:
        if value < 1:
            raise ValueError("worker and batch settings must be positive")
        return value

    @field_validator("embedding_dimension")
    @classmethod
    def valid_dimension(cls, value: int) -> int:
        if value < 1:
            raise ValueError("embedding_dimension must be positive")
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.reference_root.mkdir(parents=True, exist_ok=True)
    settings.archive_root.mkdir(parents=True, exist_ok=True)
    return settings
