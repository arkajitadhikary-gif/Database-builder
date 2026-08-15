from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class HealthComponent(BaseModel):
    name: str
    status: str
    detail: str


class SetupResponse(BaseModel):
    components: list[HealthComponent]


class DatabaseTableResponse(BaseModel):
    key: str
    label: str
    count: int
    columns: list[str]
    rows: list[dict[str, object]]


class DatabaseOverviewResponse(BaseModel):
    tables: list[DatabaseTableResponse]


class DatabaseTablePageResponse(DatabaseTableResponse):
    offset: int
    limit: int


class BatchCreateRequest(BaseModel):
    paths: list[str] = Field(min_length=1)
    recursive: bool = False


class BatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    state: str
    requested_paths: list[str]
    recursive: bool
    created_at: datetime
    item_count: int = 0
    completed_count: int = 0
    failed_count: int = 0

    @classmethod
    def from_orm(cls, value):
        return cls(
            id=value.id,
            state=value.state.value,
            requested_paths=value.requested_paths,
            recursive=value.recursive,
            created_at=value.created_at,
            item_count=len(value.items),
            completed_count=sum(item.state.value == "COMPLETED" for item in value.items),
            failed_count=sum(item.state.value.startswith("FAILED") for item in value.items),
        )


class BatchItemResponse(BaseModel):
    id: UUID
    path: str
    state: str
    attempts: int
    locked_at: datetime | None
    last_error: str | None
    document_id: UUID | None

    @classmethod
    def from_orm(cls, value):
        return cls(
            id=value.id,
            path=value.path,
            state=value.state.value,
            attempts=value.attempts,
            locked_at=value.locked_at,
            last_error=value.last_error,
            document_id=value.document_id,
        )


class EmbeddingBackfillRequest(BaseModel):
    limit: int = Field(default=100, ge=1, le=5000)
    document_id: UUID | None = None


class EmbeddingBackfillResponse(BaseModel):
    requested: int
    embedded: int
    provider: str
    model: str
    dimension: int


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    filename: str
    sha256: str
    normalized_text_hash: str | None
    byte_size: int
    page_count: int
    document_type: str
    title: str | None
    document_date: date | None
    missing_source: bool
    source_path: str
    created_at: datetime

    @classmethod
    def from_orm(cls, value):
        return cls(
            id=value.id,
            filename=value.filename,
            sha256=value.sha256,
            normalized_text_hash=value.normalized_text_hash,
            byte_size=value.byte_size,
            page_count=value.page_count,
            document_type=value.document_type.value,
            title=value.title,
            document_date=value.document_date,
            missing_source=value.missing_source,
            source_path=value.source.path,
            created_at=value.created_at,
        )


class PageResponse(BaseModel):
    id: UUID
    page_number: int
    raw_text: str
    normalized_text: str
    extraction_method: str
    text_start_offset: int | None
    text_end_offset: int | None
    ocr_engine: str | None
    ocr_confidence: float | None
    warnings: list[str]


class ReferenceResponse(BaseModel):
    id: UUID
    source_text: str
    reference_type: str
    normalized_key: str | None
    resolution_status: str
    target_document_id: UUID | None
    page_start: int
    page_end: int


class LegalSectionResponse(BaseModel):
    label: str
    heading: str | None
    text: str
    page_start: int
    page_end: int


class ActStructureResponse(BaseModel):
    name: str | None
    year: int | None
    short_title: str | None
    sections: list[LegalSectionResponse]


class JudgmentParagraphResponse(BaseModel):
    official_number: str | None
    internal_sequence: int
    text: str
    page_start: int
    page_end: int


class JudgmentStructureResponse(BaseModel):
    case_title: str | None
    court: str | None
    case_number: str | None
    decision_date: date | None
    coram_text: str | None
    paragraphs: list[JudgmentParagraphResponse]


class DocumentStructureResponse(BaseModel):
    document_id: UUID
    act: ActStructureResponse | None
    judgment: JudgmentStructureResponse | None
    references: list[ReferenceResponse]


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    mode: str = Field(default="hybrid", pattern="^(lexical|semantic|hybrid)$")

    @field_validator("query")
    @classmethod
    def non_blank_query(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("query must contain non-whitespace text")
        return value

    limit: int = Field(default=20, ge=1, le=100)
    document_type: str | None = None


class SearchHit(BaseModel):
    chunk_id: UUID
    document_id: UUID
    text: str
    document_type: str
    source_path: str
    page_start: int
    page_end: int
    section_label: str | None
    paragraph_number: str | None
    lexical_score: float | None = None
    semantic_score: float | None = None
    fused_score: float


class SearchResponse(BaseModel):
    mode: str
    hits: list[SearchHit]
    embedding_status: str
