# Judicore Architecture and Call Paths

## Authority boundary

The Python backend is authoritative. Tauri supplies a native desktop window, native path selection, backend lifecycle management, and restrictive permissions. React renders operational state obtained from FastAPI. PostgreSQL is the canonical store for documents, pages, structures, chunks, embeddings, batches, items, stage events, and errors.

## Ingestion call path

```text
Tauri dialog path
  -> React ImportView
  -> POST /api/v1/batches {paths, recursive}
  -> discover_paths
  -> PostgreSQL ingestion_batches + ingestion_items
  -> background run_batch
  -> PostgreSQL row lock / SKIP LOCKED claim
  -> validate_pdf + SHA-256
  -> PyMuPDF page extraction
  -> OCRmyPDF/Tesseract only when extraction indicates OCR is needed
  -> normalize_text + deterministic classify_document
  -> parse_legislation or parse_judgment
  -> Page + legal structure + Reference rows
  -> legal-aware Chunk rows with page ranges
  -> PostgreSQL FTS trigger
  -> optional local sentence-transformers Embedding rows
  -> VALIDATING_RESULT + COMPLETED
  -> GET /api/v1/batches and /api/v1/documents
  -> React status and library views
```

The worker persists state after each item. A process crash leaves the item, stage events, errors, and canonical rows in PostgreSQL. FastAPI startup scans non-terminal batches and resumes them. Item claims use PostgreSQL row locks with `SKIP LOCKED`, which prevents two active workers from processing the same item.

## Retrieval call path

```text
React SearchView
  -> POST /api/v1/search
  -> PostgreSQL tsquery + GIN-ranked lexical candidates
  -> local embedding provider + pgvector cosine candidates when requested
  -> reciprocal-rank fusion (RRF, k=60)
  -> SearchHit with source path, document id, page range, section/paragraph metadata
  -> React provenance result card
```

Semantic and hybrid retrieval do not manufacture vectors or scores. If the configured embedding provider or model is unavailable, the API returns a visible 503 instead of pretending the semantic path is healthy. Lexical search is a separate mode.

## Storage modes

Reference mode stores source path and cryptographic hashes while leaving originals untouched. Managed archive mode copies the exact source bytes to a content-addressed archive path after the source is validated. Missing source paths never delete canonical database rows.

## Schema safety

The initial migration enables the pgvector extension, creates the model registry tables, adds a GIN index and FTS trigger for `chunks.search_tsv`, and refuses destructive downgrade without an explicit environment guard. Additive version migrations must preserve existing canonical rows. Backups are ordinary PostgreSQL custom-format dumps and should be verified with `pg_restore --list` and the read-only verification script.

## Production hardening controls

The API supports an optional per-process bearer token. The liveness route is intentionally public for sidecar startup; all other routes require the configured token when one is present. The Tauri shell generates a 64-character token, propagates it to the FastAPI sidecar, and exposes it only to the local webview through a restricted command.

Import requests are bounded by a maximum discovered-file count and maximum PDF byte size. PostgreSQL connections use a bounded connect timeout. Worker row claims use `FOR UPDATE SKIP LOCKED`, idle polling rolls back its transaction before sleeping, and unexpected item exceptions are persisted as retryable or terminal errors according to the exception class. Batch completion is derived from item outcomes rather than assuming every item completed.

The frozen initial migration is independent of the current ORM registry. The additive hardening migration checks the expected Alembic revision, the pgvector extension, and the configured vector dimension. The read API exposes page-level raw and normalized text, Act sections, judgment paragraphs, references, and bounded embedding backfill; the desktop UI uses those APIs for inspection instead of treating browser state as canonical.
