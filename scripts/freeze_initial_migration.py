from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.db import models
from app.db.base import Base

dialect = postgresql.dialect()
tables = list(Base.metadata.sorted_tables)
enums = {
    "document_type": [item.value for item in models.DocumentType],
    "ingestion_state": [item.value for item in models.IngestionState],
    "duplicate_kind": [item.value for item in models.DuplicateKind],
    "extraction_method": [item.value for item in models.ExtractionMethod],
    "resolution_status": [item.value for item in models.ResolutionStatus],
}

def sql_literal(statement: str) -> str:
    return repr(statement.rstrip() + "\n")


lines = [
    '"""Frozen initial Judicore PostgreSQL schema. Generated once; do not derive at runtime."""',
    "# ruff: noqa: E501",
    "",
    "import os",
    "",
    "from alembic import op",
    "",
    'revision = "0001_initial"',
    "down_revision = None",
    "branch_labels = None",
    "depends_on = None",
    "",
    "",
    "def upgrade() -> None:",
    "    bind = op.get_bind()",
    '    bind.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")',
]
for name, values in enums.items():
    value_sql = ", ".join(repr(value) for value in values)
    lines.extend([
        "    bind.exec_driver_sql(",
        "        " + sql_literal(
            f"DO $$ BEGIN CREATE TYPE {name} AS ENUM ({value_sql}); "
            f"EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
        ),
        "    )",
    ])
for table in tables:
    ddl = str(CreateTable(table).compile(dialect=dialect))
    lines.extend(["    bind.exec_driver_sql(", "        " + sql_literal(ddl), "    )"])
for table in tables:
    for index in sorted(table.indexes, key=lambda value: value.name or ""):
        ddl = str(CreateIndex(index).compile(dialect=dialect))
        lines.extend(["    bind.exec_driver_sql(", "        " + sql_literal(ddl), "    )"])
lines.extend([
    "    bind.exec_driver_sql(",
    "        " + sql_literal(
        "CREATE OR REPLACE FUNCTION judicore_chunks_tsvector_update() RETURNS trigger AS $$\n"
        "BEGIN\n"
        "  NEW.search_tsv := to_tsvector('simple', coalesce(NEW.normalized_text, ''));\n"
        "  RETURN NEW;\n"
        "END;\n"
        "$$ LANGUAGE plpgsql"
    ),
    "    )",
    '    bind.exec_driver_sql("CREATE TRIGGER trg_chunks_tsvector BEFORE INSERT OR UPDATE OF normalized_text ON chunks FOR EACH ROW EXECUTE FUNCTION judicore_chunks_tsvector_update()")',
    '    bind.exec_driver_sql("UPDATE chunks SET search_tsv = to_tsvector(\'simple\', coalesce(normalized_text, \'\')) WHERE search_tsv IS NULL")',
    "",
    "",
    "def downgrade() -> None:",
    '    if os.environ.get("JUDICORE_ALLOW_DESTRUCTIVE_MIGRATIONS") != "YES":',
    '        raise RuntimeError("Destructive downgrade blocked. Restore a verified backup instead.")',
    "    bind = op.get_bind()",
    '    bind.exec_driver_sql("DROP TRIGGER IF EXISTS trg_chunks_tsvector ON chunks")',
    '    bind.exec_driver_sql("DROP FUNCTION IF EXISTS judicore_chunks_tsvector_update()")',
])
for table in reversed(tables):
    identifier = f'"{table.name}"' if table.name in {"references"} else table.name
    lines.append(
        "    bind.exec_driver_sql(" + repr(f"DROP TABLE IF EXISTS {identifier} CASCADE") + ")"
    )
for name in reversed(list(enums)):
    lines.append(f'    bind.exec_driver_sql("DROP TYPE IF EXISTS {name} CASCADE")')

(ROOT / "backend/alembic/versions/0001_initial.py").write_text("\n".join(lines) + "\n", encoding="utf-8")
