"""Add persisted AI verification runs and quarantine findings."""

from alembic import op

revision = "0005_ai_verification"
down_revision = "0004_fix_embedding_dimension"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.exec_driver_sql(
        "ALTER TYPE ingestion_state ADD VALUE IF NOT EXISTS 'REVIEW_REQUIRED'"
    )
    bind.exec_driver_sql(
        """
        CREATE TABLE verification_runs (
          id UUID NOT NULL,
          item_id UUID NOT NULL,
          provider VARCHAR(64) NOT NULL,
          model VARCHAR(255) NOT NULL,
          transfer_mode VARCHAR(32) NOT NULL,
          status VARCHAR(32) NOT NULL,
          input_sha256 VARCHAR(64) NOT NULL,
          output_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          error_message TEXT,
          created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
          updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
          PRIMARY KEY (id),
          FOREIGN KEY(item_id) REFERENCES ingestion_items (id) ON DELETE CASCADE
        )
        """
    )
    bind.exec_driver_sql(
        """
        CREATE TABLE verification_findings (
          id UUID NOT NULL,
          run_id UUID NOT NULL,
          severity VARCHAR(32) NOT NULL,
          field_name VARCHAR(128) NOT NULL,
          message TEXT NOT NULL,
          expected_value TEXT,
          observed_value TEXT,
          page_start INTEGER,
          page_end INTEGER,
          confidence FLOAT,
          evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
          decision VARCHAR(32) NOT NULL DEFAULT 'OPEN',
          PRIMARY KEY (id),
          FOREIGN KEY(run_id) REFERENCES verification_runs (id) ON DELETE CASCADE
        )
        """
    )
    bind.exec_driver_sql(
        "CREATE INDEX ix_verification_runs_item_id ON verification_runs (item_id)"
    )
    bind.exec_driver_sql(
        "CREATE INDEX ix_verification_findings_decision ON verification_findings (decision)"
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.exec_driver_sql("DROP TABLE IF EXISTS verification_findings")
    bind.exec_driver_sql("DROP TABLE IF EXISTS verification_runs")
