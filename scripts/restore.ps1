param(
  [Parameter(Mandatory=$true)][string]$BackupFile,
  [string]$DatabaseUrl = $env:DATABASE_URL,
  [switch]$ConfirmDestructive
)
$ErrorActionPreference = "Stop"
if (-not $ConfirmDestructive) { throw "Restore can overwrite target data. Re-run with -ConfirmDestructive after verifying the backup and target." }
if ([string]::IsNullOrWhiteSpace($DatabaseUrl)) { throw "Set DATABASE_URL or pass -DatabaseUrl." }
if (-not (Test-Path -LiteralPath $BackupFile -PathType Leaf)) { throw "Backup file not found: $BackupFile" }
pg_restore --dbname=$DatabaseUrl --clean --if-exists --no-owner --no-acl --exit-on-error $BackupFile
if ($LASTEXITCODE -ne 0) { throw "pg_restore failed with exit code $LASTEXITCODE" }
Write-Output "Restore completed. Run verify.ps1 against the target before using the application."
