# Judicore Stop Script (PowerShell)
$ProjectRoot = $PSScriptRoot

Write-Host "Stopping Judicore services..." -ForegroundColor Yellow

# Stop frontend and backend port listeners
$BackendConns = Get-NetTCPConnection -LocalPort 8765 -ErrorAction SilentlyContinue
foreach ($c in $BackendConns) {
    if ($c.OwningProcess -gt 0) {
        Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
    }
}

$FrontendConns = Get-NetTCPConnection -LocalPort 1420 -ErrorAction SilentlyContinue
foreach ($c in $FrontendConns) {
    if ($c.OwningProcess -gt 0) {
        Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
    }
}

Write-Host "Judicore backend and frontend stopped." -ForegroundColor Green
Write-Host "PostgreSQL container is still running in background. To stop docker container run: docker compose down" -ForegroundColor Cyan
