$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..\backend")
if (-not (Test-Path ".venv\Scripts\python.exe")) {
  py -3.12 -m venv .venv
}
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -e . pyinstaller
$modelDir = Join-Path $PSScriptRoot "..\src-tauri\resources\backend\models"
$env:JUDICORE_EMBEDDING_MODEL_DIR = $modelDir
.venv\Scripts\python.exe (Join-Path $PSScriptRoot "fetch_embedding_model.py")
.venv\Scripts\pyinstaller.exe --clean --noconfirm --onefile --name judicore-backend run.py
$target = Join-Path $PSScriptRoot "..\src-tauri\resources\backend"
New-Item -ItemType Directory -Force -Path $target | Out-Null
Copy-Item -Force "dist\judicore-backend.exe" (Join-Path $target "judicore-backend.exe")
Write-Output "Backend sidecar copied to $target"
Write-Output "This step must be run on Windows before tauri build; the sandbox cannot runtime-verify Windows packaging."
