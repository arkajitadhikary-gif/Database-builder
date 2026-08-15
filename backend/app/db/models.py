from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import get_settings
from app.db.base import Base

settings = get_settings()


class DocumentType(StrEnum):
    BARE_ACT = "BARE_ACT"
    RULE = "RULE"
    REGULATION = "REGULATION"
    NOTIFICATION = "NOTIFICATION"
    CIRCULAR = "CIRCULAR"
    ORDER = "ORDER"
    SUPREME_COURT_JUDGMENT = "SUPREME_COURT_JUDGMENT"
    HIGH_COURT_JUDGMENT = "HIGH_COURT_JUDGMENT"
    TRIBUNAL_DECISION = "TRIBUNAL_DECISION"
    OTHER_LEGAL_DOCUMENT = "OTHER_LEGAL_DOCUMENT"
    UNKNOWN = "UNKNOWN"


class IngestionState(StrEnum):
    DISCOVERED = "DISCOVERED"
    VALIDATING = "VALIDATING"
    QUEUED = "QUEUED"
    EXTRACTING = "EXTRACTING"
    OCR = "OCR"
    NORMALIZING = "NORMALIZING"
    CLASSIFYING = "CLASSIFYING"
    PARSING = "PARSING"
    CHUNKING = "CHUNKING"
    STORING = "STORING"
    INDEXING_TEXT = "INDEXING_TEXT"
    EMBEDDING = "EMBEDDING"
    VALIDATING_RESULT = "VALIDATING_RESULT"
    COMPLETED = "COMPLETED"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_TERMINAL = "FAILED_TERMINAL"
    SKIPPED_DUPLICATE = "SKIPPED_DUPLICATE"
    SKIPPED_UNSUPPORTED = "SKIPPED_UNSUPPORTED"
    CANCELLED = "CANCELLED"


class DuplicateKind(StrEnum):
    EXACT_DUPLICATE = "EXACT_DUPLICATE"
    CONTENT_DUPLICATE = "CONTENT_DUPLICATE"
    POSSIBLE_VERSION = "POSSIBLE_VERSION"
    NEW_VERSION = "NEW_VERSION"
    NEW_DOCUMENT = "NEW_DOCUMENT"


class ExtractionMethod(StrEnum):
    TEXT = "TEXT"
    OCR = "OCR"
    MIXED = "MIXED"


class ResolutionStatus(StrEnum):
    RESOLVED = "RESOLVED"
    AMBIGUOUS = "AMBIGUOUS"
    UNRESOLVED = "UNRESOLVED"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Source(Base, TimestampMixin):
    __tablename__ = "sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    path: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    storage_mode: Mapped[str] = mapped_column(String(32), default="REFERENCE", nullable=False)
    archived_path: Mapped[str | None] = mapped_column(Text)
    source_exists: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    documents: Mapped[list[Document]] = relationship(back_populates="source")


class Document(Base, TimestampMixin):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("sha256", name="uq_documents_sha256"),
        Index("ix_documents_normalized_text_hash", "normalized_text_hash"),
        Index("ix_documents_type", "document_type"),
        CheckConstraint("byte_size > 0", name="ck_documents_byte_size_positive"),
        CheckConstraint("page_count > 0", name="ck_documents_page_count_positive"),
        CheckConstraint(
            "classification_confidence IS NULL OR classification_confidence BETWEEN 0 AND 1",
            name="ck_documents_classification_confidence_range",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False
    )
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    normalized_text_hash: Mapped[str | None] = mapped_column(String(64))
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False)
    document_type: Mapped[DocumentType] = mapped_column(
        Enum(DocumentType, name="document_type", native_enum=True),
        default=DocumentType.UNKNOWN,
        nullable=False,
    )
    classification_method: Mapped[str | None] = mapped_column(String(64))
    classification_confidence: Mapped[float | None] = mapped_column()
    title: Mapped[str | None] = mapped_column(Text)
    document_date: Mapped[date | None] = mapped_column(Date)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, nullable=False
    )
    missing_source: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source: Mapped[Source] = relationship(back_populates="documents")
    pages: Mapped[list[Page]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    chunks: Mapped[list[Chunk]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    acts: Mapped[list[Act]] = relationship(back_populates="document", cascade="all, delete-orphan")
    judgments: Mapped[list[Judgment]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class Page(Base, TimestampMixin):
    __tablename__ = "pages"
    __table_args__ = (
        UniqueConstraint("document_id", "page_number", name="uq_pages_document_page"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    normalized_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    extraction_method: Mapped[ExtractionMethod] = mapped_column(
        Enum(ExtractionMethod, name="extraction_method", native_enum=True), nullable=False
    )
    text_start_offset: Mapped[int | None] = mapped_column(Integer)
    text_end_offset: Mapped[int | None] = mapped_column(Integer)
    ocr_engine: Mapped[str | None] = mapped_column(String(128))
    ocr_confidence: Mapped[float | None] = mapped_column()
    warnings: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    document: Mapped[Document] = relationship(back_populates="pages")


class Act(Base, TimestampMixin):
    __tablename__ = "acts"
    __table_args__ = (UniqueConstraint("document_id", name="uq_acts_document"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str | None] = mapped_column(Text)
    year: Mapped[int | None] = mapped_column(Integer)
    short_title: Mapped[str | None] = mapped_column(Text)
    document: Mapped[Document] = relationship(back_populates="acts")
    parts: Mapped[list[LegalPart]] = relationship(
        back_populates="act", cascade="all, delete-orphan"
    )
    sections: Mapped[list[LegalSection]] = relationship(
        back_populates="act", cascade="all, delete-orphan"
    )


class LegalPart(Base, TimestampMixin):
    __tablename__ = "legal_parts"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    act_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("acts.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    page_start: Mapped[int] = mapped_column(Integer, nullable=False)
    page_end: Mapped[int] = mapped_column(Integer, nullable=False)
    act: Mapped[Act] = relationship(back_populates="parts")
    chapters: Mapped[list[LegalChapter]] = relationship(
        back_populates="part", cascade="all, delete-orphan"
    )


class LegalChapter(Base, TimestampMixin):
    __tablename__ = "legal_chapters"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    part_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("legal_parts.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    page_start: Mapped[int] = mapped_column(Integer, nullable=False)
    page_end: Mapped[int] = mapped_column(Integer, nullable=False)
    part: Mapped[LegalPart] = relationship(back_populates="chapters")


class LegalSection(Base, TimestampMixin):
    __tablename__ = "legal_sections"
    __table_args__ = (UniqueConstraint("act_id", "label", name="uq_legal_sections_act_label"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    act_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("acts.id", ondelete="CASCADE"), nullable=False
    )
    parent_section_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("legal_sections.id", ondelete="CASCADE")
    )
    part_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("legal_parts.id", ondelete="SET NULL")
    )
    chapter_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("legal_chapters.id", ondelete="SET NULL")
    )
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    heading: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    page_start: Mapped[int] = mapped_column(Integer, nullable=False)
    page_end: Mapped[int] = mapped_column(Integer, nullable=False)
    act: Mapped[Act] = relationship(back_populates="sections")
    parent: Mapped[LegalSection | None] = relationship(
        remote_side=[id], back_populates="children"
    )
    children: Mapped[list[LegalSection]] = relationship(back_populates="parent")
    children_nodes: Mapped[list[LegalNode]] = relationship(
        back_populates="section", cascade="all, delete-orphan"
    )


class LegalNode(Base, TimestampMixin):
    __tablename__ = "legal_nodes"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    section_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("legal_sections.id", ondelete="CASCADE"), nullable=False
    )
    node_type: Mapped[str] = mapped_column(String(32), nullable=False)
    label: Mapped[str | None] = mapped_column(String(128))
    text: Mapped[str] = mapped_column(Text, nullable=False)
    page_start: Mapped[int] = mapped_column(Integer, nullable=False)
    page_end: Mapped[int] = mapped_column(Integer, nullable=False)
    section: Mapped[LegalSection] = relationship(back_populates="children_nodes")


class Judgment(Base, TimestampMixin):
    __tablename__ = "judgments"
    __table_args__ = (UniqueConstraint("document_id", name="uq_judgments_document"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    case_title: Mapped[str | None] = mapped_column(Text)
    court: Mapped[str | None] = mapped_column(Text)
    case_number: Mapped[str | None] = mapped_column(Text)
    decision_date: Mapped[datetime | None] = mapped_column(Date)
    coram_text: Mapped[str | None] = mapped_column(Text)
    document: Mapped[Document] = relationship(back_populates="judgments")
    judges: Mapped[list[JudgeLink]] = relationship(
        back_populates="judgment", cascade="all, delete-orphan"
    )
    parties: Mapped[list[Party]] = relationship(
        back_populates="judgment", cascade="all, delete-orphan"
    )
    paragraphs: Mapped[list[JudgmentParagraph]] = relationship(
        back_populates="judgment", cascade="all, delete-orphan"
    )


class Judge(Base, TimestampMixin):
    __tablename__ = "judges"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    links: Mapped[list[JudgeLink]] = relationship(back_populates="judge")


class JudgeLink(Base):
    __tablename__ = "judgment_judges"
    judgment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("judgments.id", ondelete="CASCADE"), primary_key=True
    )
    judge_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("judges.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str | None] = mapped_column(String(64))
    judgment: Mapped[Judgment] = relationship(back_populates="judges")
    judge: Mapped[Judge] = relationship(back_populates="links")


class Party(Base, TimestampMixin):
    __tablename__ = "parties"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    judgment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("judgments.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    side: Mapped[str | None] = mapped_column(String(64))
    judgment: Mapped[Judgment] = relationship(back_populates="parties")


class JudgmentParagraph(Base, TimestampMixin):
    __tablename__ = "judgment_paragraphs"
    __table_args__ = (
        UniqueConstraint("judgment_id", "internal_sequence", name="uq_judgment_paragraph_sequence"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    judgment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("judgments.id", ondelete="CASCADE"), nullable=False
    )
    official_number: Mapped[str | None] = mapped_column(String(64))
    internal_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    page_start: Mapped[int] = mapped_column(Integer, nullable=False)
    page_end: Mapped[int] = mapped_column(Integer, nullable=False)
    judgment: Mapped[Judgment] = relationship(back_populates="paragraphs")


class Reference(Base, TimestampMixin):
    __tablename__ = "references"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    reference_type: Mapped[str] = mapped_column(String(32), nullable=False)
    normalized_key: Mapped[str | None] = mapped_column(Text)
    resolution_status: Mapped[ResolutionStatus] = mapped_column(
        Enum(ResolutionStatus, name="resolution_status", native_enum=True), nullable=False
    )
    target_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL")
    )
    page_start: Mapped[int] = mapped_column(Integer, nullable=False)
    page_end: Mapped[int] = mapped_column(Integer, nullable=False)


class Chunk(Base, TimestampMixin):
    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_chunks_document_index"),
        Index("ix_chunks_search_tsv", "search_tsv", postgresql_using="gin"),
        Index("ix_chunks_document_type", "document_type"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False)
    document_type: Mapped[DocumentType] = mapped_column(
        Enum(DocumentType, name="document_type"), nullable=False
    )
    section_label: Mapped[str | None] = mapped_column(String(128))
    paragraph_number: Mapped[str | None] = mapped_column(String(64))
    page_start: Mapped[int] = mapped_column(Integer, nullable=False)
    page_end: Mapped[int] = mapped_column(Integer, nullable=False)
    source_path: Mapped[str] = mapped_column(Text, nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    search_tsv: Mapped[Any | None] = mapped_column(TSVECTOR)
    document: Mapped[Document] = relationship(back_populates="chunks")
    embeddings: Mapped[list[Embedding]] = relationship(
        back_populates="chunk", cascade="all, delete-orphan"
    )


class Embedding(Base, TimestampMixin):
    __tablename__ = "embeddings"
    __table_args__ = (
        UniqueConstraint("chunk_id", "provider", "model", name="uq_embeddings_chunk_model"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chunks.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    vector: Mapped[list[float]] = mapped_column(
        Vector(settings.embedding_dimension), nullable=False
    )
    chunk: Mapped[Chunk] = relationship(back_populates="embeddings")


class IngestionBatch(Base, TimestampMixin):
    __tablename__ = "ingestion_batches"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    state: Mapped[IngestionState] = mapped_column(
        Enum(IngestionState, name="ingestion_state"), nullable=False
    )
    requested_paths: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    recursive: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    pause_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    items: Mapped[list[IngestionItem]] = relationship(
        back_populates="batch", cascade="all, delete-orphan"
    )


class IngestionItem(Base, TimestampMixin):
    __tablename__ = "ingestion_items"
    __table_args__ = (
        UniqueConstraint("batch_id", "path", name="uq_ingestion_items_batch_path"),
        Index("ix_ingestion_items_state", "state"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    batch_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ingestion_batches.id", ondelete="CASCADE"), nullable=False
    )
    path: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[IngestionState] = mapped_column(
        Enum(IngestionState, name="ingestion_state"), nullable=False
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL")
    )
    batch: Mapped[IngestionBatch] = relationship(back_populates="items")
    events: Mapped[list[StageEvent]] = relationship(
        back_populates="item", cascade="all, delete-orphan"
    )
    errors: Mapped[list[IngestionError]] = relationship(
        back_populates="item", cascade="all, delete-orphan"
    )


class StageEvent(Base):
    __tablename__ = "stage_events"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ingestion_items.id", ondelete="CASCADE"), nullable=False
    )
    stage: Mapped[IngestionState] = mapped_column(
        Enum(IngestionState, name="ingestion_state"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    item: Mapped[IngestionItem] = relationship(back_populates="events")


class IngestionError(Base):
    __tablename__ = "ingestion_errors"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ingestion_items.id", ondelete="CASCADE"), nullable=False
    )
    stage: Mapped[IngestionState] = mapped_column(
        Enum(IngestionState, name="ingestion_state"), nullable=False
    )
    error_type: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    retryable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    item: Mapped[IngestionItem] = relationship(back_populates="errors")


class DuplicateRecord(Base, TimestampMixin):
    __tablename__ = "duplicates"
    __table_args__ = (
        UniqueConstraint("document_id", "related_document_id", name="uq_duplicate_pair"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    related_document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[DuplicateKind] = mapped_column(
        Enum(DuplicateKind, name="duplicate_kind"), nullable=False
    )
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class DocumentVersion(Base, TimestampMixin):
    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "related_document_id", name="uq_document_version_pair"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    related_document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    relation: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class SystemSetting(Base, TimestampMixin):
    __tablename__ = "system_settings"
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
