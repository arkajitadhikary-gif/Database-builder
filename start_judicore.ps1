# Judicore 1-Click Startup Script (PowerShell)
$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot

Write-Host "==============================================" -ForegroundColor Cyan
Write-Host "   Judicore Legal Database Builder - Starting  " -ForegroundColor Cyan
Write-Host "==============================================" -ForegroundColor Cyan

# 1. Start PostgreSQL with pgvector via Docker Compose
Write-Host "`n[1/4] Ensuring PostgreSQL container is running..." -ForegroundColor Yellow
try {
    & docker compose -f "$ProjectRoot\docker-compose.yml" up -d postgres
    Write-Host "PostgreSQL container is active on 127.0.0.1:55432" -ForegroundColor Green
} catch {
    Write-Host "Warning: Could not start docker container. Ensure Docker Desktop is running." -ForegroundColor Red
}

# 2. Check and start Backend
Write-Host "`n[2/4] Starting FastAPI backend on http://127.0.0.1:8765..." -ForegroundColor Yellow
$BackendRunning = Get-NetTCPConnection -LocalPort 8765 -ErrorAction SilentlyContinue
if (-not $BackendRunning) {
    Start-Process -FilePath "powershell.exe" -ArgumentList "-NoExit", "-Command", "cd '$ProjectRoot\backend'; Write-Host 'Starting Judicore Backend...' -ForegroundColor Cyan; uv run python run.py --host 127.0.0.1 --port 8765" -WindowStyle Minimized
    Start-Sleep -Seconds 3
    Write-Host "Judicore Backend process started." -ForegroundColor Green
} else {
    Write-Host "Judicore Backend is already running on port 8765." -ForegroundColor Green
}

# 3. Check and start Frontend
Write-Host "`n[3/4] Starting React/Vite frontend on http://127.0.0.1:1420..." -ForegroundColor Yellow
$FrontendRunning = Get-NetTCPConnection -LocalPort 1420 -ErrorAction SilentlyContinue
if (-not $FrontendRunning) {
    Start-Process -FilePath "powershell.exe" -ArgumentList "-NoExit", "-Command", "cd '$ProjectRoot\frontend'; Write-Host 'Starting Judicore Frontend...' -ForegroundColor Cyan; pnpm dev" -WindowStyle Minimized
    Start-Sleep -Seconds 2
    Write-Host "Judicore Frontend process started." -ForegroundColor Green
} else {
    Write-Host "Judicore Frontend is already running on port 1420." -ForegroundColor Green
}

# 4. Open in browser
Write-Host "`n[4/4] Opening Judicore UI in your browser..." -ForegroundColor Yellow
Start-Process "http://127.0.0.1:1420"

Write-Host "`nJudicore is ready and accessible at http://127.0.0.1:1420" -ForegroundColor Green
Write-Host "Backend API is at http://127.0.0.1:8765/docs" -ForegroundColor Green
Write-Host "==============================================" -ForegroundColor Cyan
