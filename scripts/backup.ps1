param(
  [string]$OutputDirectory = ".\backups",
  [string]$DatabaseUrl = $env:DATABASE_URL
)
$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($DatabaseUrl)) { throw "Set DATABASE_URL or pass -DatabaseUrl." }
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$outFile = Join-Path $OutputDirectory "judicore-$stamp.dump"
pg_dump --dbname=$DatabaseUrl --format=custom --file=$outFile --no-owner --no-acl
if ($LASTEXITCODE -ne 0) { throw "pg_dump failed with exit code $LASTEXITCODE" }
pg_restore --list $outFile | Out-File (Join-Path $OutputDirectory "judicore-$stamp.contents.txt")
Write-Output "Backup created: $outFile"
