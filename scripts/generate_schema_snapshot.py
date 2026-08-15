from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.db import models  # noqa: F401
from app.db.base import Base

dialect = postgresql.dialect()
for table in Base.metadata.sorted_tables:
    print(str(CreateTable(table).compile(dialect=dialect)).rstrip() + ";\n")
for table in Base.metadata.sorted_tables:
    for index in sorted(table.indexes, key=lambda value: value.name or ""):
        print(str(CreateIndex(index).compile(dialect=dialect)).rstrip() + ";\n")
