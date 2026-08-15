"""Align embedding vector column with the runtime embedding dimension."""

from alembic import op

revision = "0004_fix_embedding_dimension"
down_revision = "0003_schema_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
    bind.exec_driver_sql(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = 'embeddings'
              AND column_name = 'vector'
              AND data_type = 'USER-DEFINED'
          ) THEN
            ALTER TABLE embeddings
              ALTER COLUMN vector TYPE vector(384);
          END IF;
        END $$;
        """
    )
    bind.exec_driver_sql("ALTER TABLE embeddings ALTER COLUMN vector TYPE vector(384)")
    bind.exec_driver_sql(
        """
        UPDATE embeddings
        SET dimension = 384
        WHERE dimension IS DISTINCT FROM 384;
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.exec_driver_sql(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = 'embeddings'
              AND column_name = 'vector'
              AND udt_name = 'vector'
          ) THEN
            ALTER TABLE embeddings
              ALTER COLUMN vector TYPE vector(380);
          END IF;
        END $$;
        """
    )
    bind.exec_driver_sql(
        """
        UPDATE embeddings
        SET dimension = 380
        WHERE dimension IS DISTINCT FROM 380;
        """
    )
