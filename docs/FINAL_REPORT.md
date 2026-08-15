## IMPLEMENTED

The Judicore repository has been hardened beyond the initial implementation. The authoritative backend remains FastAPI with SQLAlchemy 2, Alembic, psycopg, PostgreSQL UUID/JSONB/TSVECTOR, pgvector, normalized legal entities, durable ingestion state, page provenance, full-text search, local embeddings, and RRF hybrid retrieval.

The initial Alembic migration is now a frozen PostgreSQL DDL snapshot. It no longer calls `Base.metadata.create_all()` and no longer depends on the current ORM registry at runtime. The additive migrations are idempotent where possible, refuse destructive downgrade by default, unify the native enum types, and add document integrity constraints for positive size/page counts and classification-confidence range. Schema readiness now checks the expected Alembic revision, the pgvector extension, and the configured vector dimension.

The ingestion worker now has bounded discovery and file-size controls, persistent missing-source marking, explicit unsupported-file states, duplicate handling, failure-derived batch terminal states, unexpected-exception persistence, row locking with `SKIP LOCKED`, rollback-before-idle-polling, startup stale-item recovery, and duplicate-task suppression in the API process. Unsupported files are not requeued by the normal retry action. Embedding backfill is a bounded, row-locked API operation for chunks that lack a compatible provider/model/dimension vector.

The PDF/OCR path now honors the OCR-enabled setting and preserves mixed provenance: pages with existing text remain `TEXT`, pages that required OCR are `OCR`, and pages with partial existing text plus OCR enrichment are `MIXED`. OCR subprocesses remain timeout-bounded and source PDFs are never modified in place. Recursive imports and individual PDF sizes are bounded by configuration.

The retrieval path now uses the indexed `search_tsv` column directly for lexical search, reports `NO_INDEXED_VECTORS` when semantic candidates do not exist, and changes hybrid response status to `hybrid:semantic-unavailable` rather than implying a complete hybrid result. Search queries reject whitespace-only input. The embedding provider is process-scoped, validates runtime dimension, performs real inference, and has no synthetic fallback.

The React/Tauri desktop application now includes a real document inspector for raw versus normalized page text, page-level extraction metadata, Act sections, judgment paragraphs, and references. Ingestion jobs expose persisted item diagnostics and progress counts. Settings includes a real missing-embedding backfill action. Interactive table rows are keyboard accessible, job action errors are visible, and frontend requests have timeouts.

The packaged Tauri shell now generates a per-process 64-character session token, passes it to the FastAPI sidecar, authenticates health/API calls, retrieves it only through a restricted local command, redirects packaged storage to the per-user application-data directory, and prefers a packaged local embedding model. The Windows build script downloads the configured model into the Tauri resource tree before packaging the PyInstaller sidecar.

| Area | Hardening status |
| --- | --- |
| Frozen migrations and schema checks | **Implemented** |
| Durable worker exception/retry semantics | **Implemented** |
| Import ceilings and connection timeouts | **Implemented** |
| OCR mixed-provenance handling | **Implemented** |
| Embedding backfill and runtime dimension validation | **Implemented** |
| Search status truthfulness | **Implemented** |
| Authenticated Tauri/FastAPI local channel | **Implemented** |
| Document/page/structure inspection | **Implemented** |
| Windows/Tauri compilation | Source is implemented; runtime unavailable in this sandbox |

## VERIFIED

Fresh checks executed after the hardening pass include strict backend Ruff lint, Python compilation, the complete backend test suite, strict frontend TypeScript compilation, the Vite production bundle, real local embedding inference, configuration JSON parsing, `git diff --check`, and a real HTTP token-authentication exercise.

The authenticated process test started FastAPI on `127.0.0.1:8766` with `SESSION_TOKEN=test-token`. `GET /api/v1/health/live` returned HTTP 200 without authentication, an unauthenticated `GET /api/v1/health` returned HTTP 401, and the bearer-authenticated health request returned HTTP 200 with truthful degraded status because PostgreSQL was unavailable. This verifies that the Tauri token naming defect found during the hardening pass is fixed.

## TEST RESULTS

The final backend test command returned:

```text
14 passed, 2 skipped in 0.58s
```

The fourteen passing tests cover PDF validation and hashing, bounded discovery, file-size rejection, invalid-PDF isolation, conservative normalization, source-derived classification, legislation structure and page ranges, judgment paragraph numbering, multi-page extraction, whitespace-query rejection, OCR-disabled behavior, ORM integrity constraints, and authenticated/degraded health behavior. The two skipped tests are opt-in PostgreSQL integration tests because no PostgreSQL server or container runtime is present and `JUDICORE_TEST_DATABASE_URL` is unset.

Strict backend Ruff lint and Python compilation passed for `backend` and `scripts`. The frontend passed strict TypeScript compilation and Vite production build. The final bundle measured approximately 0.47 kB HTML, 19.06 kB CSS, and 232.67 kB JavaScript before gzip compression.

## DATABASE VERIFICATION

Live PostgreSQL verification remains unavailable in this sandbox. `psql`, `postgres`, `pg_config`, `initdb`, Docker, Podman, and nerdctl are not installed. The optional runtime probe returned `postgresql.ready: false` with `OperationalError`. Therefore no live canonical counts, migration execution, pgvector index, FTS query, transaction rollback, or persisted embedding count is claimed.

The production path is documented and isolated: PostgreSQL 16 plus pgvector, `alembic upgrade head`, a separate integration database, and the read-only PowerShell verification script. The schema readiness endpoint will not report READY until the expected migration, extension, and vector dimension are all present.

## PDF EXTRACTION VERIFICATION

Real PyMuPDF extraction was verified against generated test-only PDFs with per-page provenance and multi-page ordering. The refreshed bounded stress run processed 24 pages from 8 PDFs with 3 pages each using 2 configured workers. It measured 0.0166 seconds elapsed, 133,526 peak Python memory bytes, and `bounded_concurrency: true`.

The source pipeline revalidates the PDF after discovery and before extraction, applies the configured byte ceiling, preserves raw and normalized page text, and records extraction method and warnings. These behaviors are covered by the passing unit suite.

## OCR VERIFICATION

The OCR branch is implemented with OCRmyPDF/Tesseract discovery, timeout handling, captured subprocess errors, OCR enablement checks, and mixed page-level provenance. Runtime OCR execution was not possible because the sandbox reports `missing ocrmypdf, tesseract`. No OCR confidence values or OCR output are fabricated. Windows acceptance still requires a mixed text/scanned corpus with both executables installed.

## LEGAL PARSER VERIFICATION

The deterministic source-derived parser is implemented and unit-tested for generic Act/Part/Chapter/Section structures, judgment paragraph numbers, courts, case-like headings, dates, statutory references, and unresolved citations. Exact source text and page ranges remain persisted. The document inspector exposes those persisted structures instead of rendering hardcoded legal content.

## RETRIEVAL VERIFICATION

The lexical, semantic, and hybrid call paths are implemented with PostgreSQL FTS, pgvector cosine distance, metadata filtering, and RRF with `k=60`. Search results carry source path, document id, page range, section/paragraph context, and component scores. The local embedding model loaded successfully and produced a real 384-dimensional vector during the optional-runtime probe.

A live PostgreSQL FTS query, pgvector query, hybrid result over persisted rows, and end-to-end embedding backfill were not runtime verified because PostgreSQL is unavailable. The API now reports this state rather than presenting a semantic-ready label without indexed vectors.

## RESTART / RESUME VERIFICATION

The restart/resume design is implemented through durable batches/items/stage events/errors, terminal states, `SKIP LOCKED` claims, stale lock cleanup, startup recovery, and explicit pause/resume/cancel/retry controls. Unexpected exceptions are persisted and batch state is derived from item outcomes.

A real interrupted PostgreSQL ingestion and process restart was not executed in this sandbox because the required database runtime is absent. This remains a required Windows/PostgreSQL acceptance test rather than an unverified claim.

## DUPLICATE VERIFICATION

Binary SHA-256 duplicate detection is implemented and tested at the hashing layer. Exact duplicates are persisted as `SKIPPED_DUPLICATE`; normalized-text duplicates receive evidence records rather than being silently dropped. Missing source paths mark existing canonical records without deleting them. A live duplicate import against PostgreSQL was not executed because the database is unavailable.

## NOT RUNTIME VERIFIED

Windows 11 x64 Tauri compilation and MSI/NSIS packaging; PyInstaller sidecar execution on Windows; PostgreSQL 16 and pgvector startup; Alembic execution against a live database; FTS and pgvector queries; OCRmyPDF/Tesseract output; full real-corpus ingestion; live duplicate/relink behavior; process-interruption restart/resume; and packaged local-model loading remain environment-blocked.

These are explicit runtime boundaries. The source implementation, scripts, tests, and operator instructions are present, but the unavailable dependencies prevent an honest claim that those acceptance paths passed here.

## KNOWN LIMITATIONS

The parser is generic and deterministic. It does not claim authoritative legal-semantic interpretation, amendment resolution, case identity resolution, or citation resolution. Uncertain references stay `UNRESOLVED`. Document-version evidence is modeled additively but is not yet populated by a probabilistic comparison workflow.

The desktop UI is inspection-oriented and operational. It now exposes persisted pages, structure, references, and batch diagnostics, but it does not expose destructive reset operations, which is intentional. The backend still requires PostgreSQL for canonical persistence, FTS, pgvector, and durable worker state.

## WINDOWS PREREQUISITES

Install Python 3.12, `uv`, Node.js 22, pnpm, Rust with the MSVC toolchain, Visual Studio Build Tools with Desktop development with C++, WebView2, PostgreSQL 16, pgvector, Tesseract, OCRmyPDF, Git, and the Tauri CLI. Use a dedicated Judicore database and a separate integration-test database.

Run `scripts/build_backend_windows.ps1` from the repository root. It installs the backend, fetches the configured embedding model into `src-tauri/resources/backend/models`, builds `judicore-backend.exe`, and copies it into `src-tauri/resources/backend`. Then run `cargo tauri build --manifest-path src-tauri\tauri.conf.json`.

## RUN THE APPLICATION

For backend development:

```powershell
Copy-Item .env.example .env
cd backend
uv sync --dev
uv run alembic upgrade head
uv run python run.py --host 127.0.0.1 --port 8765
```

For the frontend during development:

```powershell
cd frontend
pnpm install
pnpm dev
```

For the packaged desktop application, build the Windows sidecar first and then build Tauri. The Tauri shell refuses to start if the sidecar is absent or the public liveness gate does not succeed within 30 seconds. The packaged sidecar receives a generated bearer token and uses per-user application-data storage.

## INGEST MY PDF OR FOLDER

Use **Import documents** and choose individual PDFs or a folder. The backend receives filesystem paths, persists discovery, enforces `MAX_DISCOVERED_FILES` and `MAX_PDF_BYTES`, hashes bytes, validates and extracts pages, runs OCR only when configured and needed, parses source-derived legal structures, persists provenance, creates chunks, and attempts embeddings. Unsupported files are recorded as `SKIPPED_UNSUPPORTED`; they are not silently ignored.

Use **Ingestion jobs** for persisted progress and item errors. Use **Document library** to open the inspection drawer, switch between raw and normalized page text, inspect extraction metadata, view Act sections or judgment paragraphs, and review references. Use **Settings → Retry missing embeddings** after the PostgreSQL schema is ready if a prior model outage left chunks without vectors.

## BACKUP / RESTORE

Create a custom-format PostgreSQL backup with:

```powershell
.\scripts\backup.ps1 -DatabaseUrl $env:DATABASE_URL
```

Restore only with an explicit destructive confirmation:

```powershell
.\scripts\restore.ps1 -BackupFile .\backups\judicore-YYYYMMDD-HHMMSS.dump -DatabaseUrl $env:DATABASE_URL -ConfirmDestructive
```

Then run:

```powershell
.\scripts\verify.ps1 -DatabaseUrl $env:DATABASE_URL
```

Never restore over production without a separately verified backup and a reviewed target connection string.

## FUTURE JUDICORE INTEGRATION

The stable read boundary is the FastAPI `/api/v1` surface. Future Judicore services can consume health/setup, durable batch state and item diagnostics, documents, pages, Act structures, judgment paragraphs, references, embeddings/backfill status, and provenance-backed lexical/semantic/hybrid retrieval. AI legal chat, drafting, agents, web search, and answer generation remain outside this repository’s scope.
