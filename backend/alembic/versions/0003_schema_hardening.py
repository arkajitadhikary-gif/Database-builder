"""Harden existing schemas without dropping canonical data."""

from alembic import op

revision = "0003_schema_hardening"
down_revision = "0002_document_versions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    statements = [
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'chunk_document_type') THEN
            ALTER TABLE chunks
              ALTER COLUMN document_type TYPE document_type
              USING document_type::text::document_type;
            DROP TYPE chunk_document_type;
          END IF;
        END $$;
        """,
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'item_ingestion_state') THEN
            ALTER TABLE ingestion_items
              ALTER COLUMN state TYPE ingestion_state
              USING state::text::ingestion_state;
            DROP TYPE item_ingestion_state;
          END IF;
        END $$;
        """,
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'stage_event_state') THEN
            ALTER TABLE stage_events
              ALTER COLUMN stage TYPE ingestion_state
              USING stage::text::ingestion_state;
            DROP TYPE stage_event_state;
          END IF;
        END $$;
        """,
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'ingestion_error_state') THEN
            ALTER TABLE ingestion_errors
              ALTER COLUMN stage TYPE ingestion_state
              USING stage::text::ingestion_state;
            DROP TYPE ingestion_error_state;
          END IF;
        END $$;
        """,
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'ck_documents_byte_size_positive'
          ) THEN
            ALTER TABLE documents ADD CONSTRAINT ck_documents_byte_size_positive
              CHECK (byte_size > 0);
          END IF;
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'ck_documents_page_count_positive'
          ) THEN
            ALTER TABLE documents ADD CONSTRAINT ck_documents_page_count_positive
              CHECK (page_count > 0);
          END IF;
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'ck_documents_classification_confidence_range'
          ) THEN
            ALTER TABLE documents ADD CONSTRAINT ck_documents_classification_confidence_range
              CHECK (
                classification_confidence IS NULL
                OR classification_confidence BETWEEN 0 AND 1
              );
          END IF;
        END $$;
        """,
    ]
    for statement in statements:
        bind.exec_driver_sql(statement)


def downgrade() -> None:
    raise RuntimeError(
        "Schema hardening is intentionally non-reversible; restore a verified backup instead."
    )
