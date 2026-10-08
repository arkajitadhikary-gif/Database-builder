param(
  [string]$DatabaseUrl = $env:DATABASE_URL
)
$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($DatabaseUrl)) { throw "Set DATABASE_URL or pass -DatabaseUrl." }
$queries = @(
  "SELECT current_database(), current_user",
  "SELECT extname FROM pg_extension WHERE extname = 'vector'",
  "SELECT version_num FROM alembic_version",
  "SELECT 'documents' AS table_name, count(*) FROM documents UNION ALL SELECT 'pages', count(*) FROM pages UNION ALL SELECT 'chunks', count(*) FROM chunks UNION ALL SELECT 'embeddings', count(*) FROM embeddings UNION ALL SELECT 'ingestion_batches', count(*) FROM ingestion_batches UNION ALL SELECT 'ingestion_items', count(*) FROM ingestion_items"
)
foreach ($query in $queries) {
  psql --dbname=$DatabaseUrl --tuples-only --no-align --command=$query
  if ($LASTEXITCODE -ne 0) { throw "psql verification query failed with exit code $LASTEXITCODE" }
}
