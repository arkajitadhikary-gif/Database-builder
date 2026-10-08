"""Add universal extracted tables and rows for any PDF document."""

from alembic import op

revision = "0006_universal_tables"
down_revision = "0005_ai_verification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS extracted_tables (
          id UUID NOT NULL,
          document_id UUID NOT NULL,
          table_name VARCHAR(255) NOT NULL,
          table_slug VARCHAR(255) NOT NULL,
          document_category VARCHAR(128) NOT NULL DEFAULT 'General Document',
          description TEXT,
          columns JSONB NOT NULL DEFAULT '[]'::jsonb,
          row_count INTEGER NOT NULL DEFAULT 0,
          created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
          updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
          PRIMARY KEY (id),
          FOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE CASCADE
        )
        """
    )
    bind.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS extracted_rows (
          id UUID NOT NULL,
          table_id UUID NOT NULL,
          row_index INTEGER NOT NULL,
          data JSONB NOT NULL DEFAULT '{}'::jsonb,
          source_page INTEGER,
          confidence FLOAT,
          created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
          updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
          PRIMARY KEY (id),
          FOREIGN KEY(table_id) REFERENCES extracted_tables (id) ON DELETE CASCADE
        )
        """
    )
    bind.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_extracted_tables_document_id ON extracted_tables (document_id)"
    )
    bind.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_extracted_tables_category ON extracted_tables (document_category)"
    )
    bind.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_extracted_rows_table_id ON extracted_rows (table_id)"
    )
    bind.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_extracted_rows_table_index ON extracted_rows (table_id, row_index)"
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.exec_driver_sql("DROP TABLE IF EXISTS extracted_rows")
    bind.exec_driver_sql("DROP TABLE IF EXISTS extracted_tables")
