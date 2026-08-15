"""Add document version evidence records without changing canonical documents."""

import os

from alembic import op

revision = "0002_document_versions"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


_DOCUMENT_VERSIONS_DDL = """
CREATE TABLE IF NOT EXISTS document_versions (
    id UUID NOT NULL,
    document_id UUID NOT NULL,
    related_document_id UUID NOT NULL,
    relation VARCHAR(32) NOT NULL,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    PRIMARY KEY (id),
    CONSTRAINT uq_document_version_pair UNIQUE (document_id, related_document_id),
    FOREIGN KEY (document_id) REFERENCES documents (id) ON DELETE CASCADE,
    FOREIGN KEY (related_document_id) REFERENCES documents (id) ON DELETE CASCADE
)
"""


def upgrade() -> None:
    op.get_bind().exec_driver_sql(_DOCUMENT_VERSIONS_DDL)


def downgrade() -> None:
    if os.environ.get("JUDICORE_ALLOW_DESTRUCTIVE_MIGRATIONS") != "YES":
        raise RuntimeError("Destructive downgrade blocked without explicit authorization")
    op.get_bind().exec_driver_sql("DROP TABLE IF EXISTS document_versions CASCADE")
