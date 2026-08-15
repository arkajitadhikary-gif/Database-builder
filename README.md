# Judicore Legal Database Builder

Judicore is a local-first Windows desktop application for converting user-selected Indian legal PDFs into a durable, structured, searchable PostgreSQL corpus. The source PDF remains authoritative. The system preserves the original path and SHA-256 digest, each page’s raw and normalized text, deterministic legal structure, page provenance, retrieval chunks, and optional embeddings.

The canonical implementation is split into a **Tauri 2 desktop shell**, a **React + TypeScript UI**, and an authoritative **FastAPI + SQLAlchemy + Alembic backend**. The backend owns discovery, validation, hashing, PyMuPDF extraction, OCR branching, normalization, classification, legal parsing, persistence, full-text indexing, embeddings, and retrieval. The frontend never stores canonical state in browser memory or local storage.

## Repository layout

| Path | Responsibility |
| --- | --- |
| `backend/app` | FastAPI API, SQLAlchemy models, ingestion worker, PDF/OCR/parsers, chunking, embeddings, retrieval |
| `backend/alembic` | PostgreSQL schema migration and pgvector/FTS trigger setup |
| `frontend/src` | Desktop operational UI and typed backend client |
| `src-tauri` | Tauri 2 shell, restricted capabilities, backend sidecar bootstrap and shutdown |
| `scripts` | Windows sidecar build and PostgreSQL backup/restore/verification scripts |
| `docs` | Architecture and runtime/acceptance notes |
| `storage` | Project-local reference/archive roots; originals are never modified automatically |

## Run the backend

The backend requires Python 3.12+, PostgreSQL 16 with the `vector` extension, and optional Tesseract plus OCRmyPDF for scanned documents. Copy `.env.example` to `.env`, configure `DATABASE_URL`, create the database, then run:

```powershell
cd backend
uv sync --dev
uv run alembic upgrade head
uv run python run.py --host 127.0.0.1 --port 8765
```

The health endpoints are `GET /api/v1/health/live`, `GET /api/v1/health`, and `GET /api/v1/setup`. They report actual dependency state; they do not synthesize readiness. When `SESSION_TOKEN` or `JUDICORE_SESSION_TOKEN` is configured, only the liveness endpoint is public; all other API calls require `Authorization: Bearer <token>`. The packaged Tauri shell generates this token per process and sends it to the sidecar and frontend through a restricted command.

## Optional local PostgreSQL stack

If Docker Desktop is available on Windows, the isolated development database can be started with:

```powershell
docker compose up -d postgres
```

The compose file binds PostgreSQL to loopback only. It does not overwrite an existing PostgreSQL installation. Run migrations before importing documents.

## Run the frontend

```powershell
cd frontend
pnpm install
pnpm dev
```

The Tauri UI uses the native dialog plugin to send filesystem paths directly to the backend. It does not upload entire folders through browser memory. During a desktop build, Tauri runs the frontend and connects it to the local FastAPI endpoint.

## Build the Windows desktop package

The sandbox used to develop this repository does not contain the Windows Rust/Tauri toolchain, PostgreSQL server, pgvector extension, or OCR executables. On a Windows build machine, install Rust, Visual Studio Build Tools with the desktop C++ workload, WebView2, Node.js, pnpm, Python 3.12, PostgreSQL 16, pgvector, Tesseract, and OCRmyPDF. Then run:

```powershell
.\scripts\build_backend_windows.ps1
cargo install tauri-cli --version ^2
cargo tauri build --manifest-path src-tauri\tauri.conf.json
```

The sidecar build script packages `backend/run.py` as `judicore-backend.exe`, downloads the configured embedding model into `src-tauri/resources/backend/models`, and copies the sidecar into `src-tauri/resources/backend`. Tauri refuses to start when the sidecar is absent or when the liveness endpoint does not become healthy within 30 seconds. Packaged storage is redirected to the per-user Tauri application-data directory, not the install directory.

## Ingestion and retrieval

A batch follows the durable path `Discovery → Validation → SHA-256 → Duplicate/Version Analysis → Page Extraction → OCR Decision/Execution → Raw Text → Normalization → Classification → Legal Parsing → Metadata → Page Provenance → Legal-Aware Chunking → PostgreSQL → FTS → Embeddings/pgvector → Validation → Completed`. Unsupported files are persisted as `SKIPPED_UNSUPPORTED`. Exact duplicates are skipped by binary SHA-256, while normalized-text duplicates are preserved with a duplicate evidence record rather than silently discarded.

The retrieval API supports PostgreSQL FTS, pgvector cosine similarity, metadata filtering, and reciprocal-rank fusion for hybrid retrieval. Every result includes source path, page range, document type, and section or paragraph metadata. Semantic and hybrid search report `NO_INDEXED_VECTORS` when embeddings are not persisted instead of implying semantic coverage. `POST /api/v1/embeddings/backfill` performs a bounded, row-locked retry for missing vectors. `GET /api/v1/documents/{id}/pages` and `GET /api/v1/documents/{id}/structure` expose persisted raw/normalized pages, Act sections, judgment paragraphs, and references for inspection.

## Production hardening boundaries

The initial Alembic migration is a frozen schema snapshot and no longer depends on the current ORM metadata at runtime. `0003_schema_hardening` checks the expected migration revision, pgvector availability, vector dimension, and document integrity constraints. Migrations never drop production data unless `JUDICORE_ALLOW_DESTRUCTIVE_MIGRATIONS=YES` is explicitly set. Backup and restore scripts require a deliberate confirmation switch for destructive restore.

Recursive imports are bounded by `MAX_DISCOVERED_FILES`, individual PDFs by `MAX_PDF_BYTES`, database connections by `DATABASE_CONNECT_TIMEOUT_SECONDS`, and OCR by `OCR_TIMEOUT_SECONDS`. Missing source paths do not delete canonical rows; they mark the canonical record as missing and preserve its provenance. No legal facts or production corpus data are seeded by this repository.
