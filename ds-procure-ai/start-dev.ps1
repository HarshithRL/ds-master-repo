# Mate local dev — opens 4 terminals: Flask :5000, Vite :5173, AI Brain :8004, MLflow :5001
# Usage (from repo root): .\start-dev.ps1

$ErrorActionPreference = "Stop"

$RepoRoot = $PSScriptRoot
$VenvActivate = Join-Path $RepoRoot ".venv\Scripts\Activate.ps1"
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$DatabricksProfile = "adb-7181820732839861"
$MlflowTrackingUri = "http://127.0.0.1:5001"
$MateSqlite = Join-Path $RepoRoot "mate.sqlite"
$MateProjects = Join-Path $RepoRoot "data\projects"
$PidFile = Join-Path $RepoRoot ".mate-dev.pids"

if (-not (Test-Path $Python)) {
    Write-Error "Python venv not found at $Python. Run: python -m venv .venv; pip install -r requirements.txt"
}

function Start-MateTerminal {
    param(
        [string]$Title,
        [string]$Body
    )

    $command = @"
`$Host.UI.RawUI.WindowTitle = '$Title'
$Body
"@

    $proc = Start-Process powershell.exe -ArgumentList "-NoExit", "-Command", $command -PassThru
    return $proc.Id
}

$activate = ". '$VenvActivate'"
$shellPids = @()

# Stage 1 — Flask API (must run from backend/)
$shellPids += Start-MateTerminal -Title "Mate 1/4 · Flask :5000" -Body @"
Set-Location '$RepoRoot\backend'
$activate
`$env:DATABRICKS_CONFIG_PROFILE = '$DatabricksProfile'
`$env:BRAIN_BASE_URL = 'http://127.0.0.1:8004'
`$env:MATE_SQLITE_PATH = '$MateSqlite'
`$env:MATE_PROJECTS_DATA_ROOT = '$MateProjects'
Write-Host ''
Write-Host '=== Mate Flask API ===' -ForegroundColor Cyan
Write-Host 'http://127.0.0.1:5000' -ForegroundColor Green
Write-Host ''
& '$Python' app.py
"@

Start-Sleep -Milliseconds 400

# Stage 2 — React / Vite
$shellPids += Start-MateTerminal -Title "Mate 2/4 · Frontend :5173" -Body @"
Set-Location '$RepoRoot\frontend'
Write-Host ''
Write-Host '=== Mate Frontend (Vite) ===' -ForegroundColor Cyan
Write-Host 'http://localhost:5173' -ForegroundColor Green
Write-Host ''
npm run dev
"@

Start-Sleep -Milliseconds 400

# Stage 3 — MLflow tracking UI (port 5001; Flask already uses 5000)
# Start before AI Brain so traces can reach the server. Reuses ./mlruns when present.
$shellPids += Start-MateTerminal -Title "Mate 4/4 · MLflow :5001" -Body @"
Set-Location '$RepoRoot'
$activate
Write-Host ''
Write-Host '=== Mate MLflow Tracking UI ===' -ForegroundColor Cyan
Write-Host '$MlflowTrackingUri' -ForegroundColor Green
Write-Host ''
& '$Python' -m mlflow server --host 127.0.0.1 --port 5001 --workers 1
"@

Start-Sleep -Milliseconds 800

# Stage 4 — AI Brain AgentServer (workspace chat + insights)
$shellPids += Start-MateTerminal -Title "Mate 3/4 · AI Brain :8004" -Body @"
Set-Location '$RepoRoot'
$activate
`$env:DATABRICKS_CONFIG_PROFILE = '$DatabricksProfile'
`$env:PYTHONPATH = '$RepoRoot'
`$env:MLFLOW_TRACKING_URI = '$MlflowTrackingUri'
`$env:MLFLOW_EXPERIMENT_NAME = 'ai_brain'
`$env:MATE_SQLITE_PATH = '$MateSqlite'
`$env:MATE_PROJECTS_DATA_ROOT = '$MateProjects'
Write-Host ''
Write-Host '=== Mate AI Brain ===' -ForegroundColor Cyan
Write-Host 'http://127.0.0.1:8004/health' -ForegroundColor Green
Write-Host 'MLflow traces -> $MlflowTrackingUri' -ForegroundColor DarkGray
Write-Host ''
& '$Python' -m ai_brain.brain_server
"@

$shellPids | Set-Content -Path $PidFile -Encoding ascii

Write-Host ""
Write-Host "Started 4 terminals:" -ForegroundColor Green
Write-Host "  1. Flask API     -> http://127.0.0.1:5000"
Write-Host "  2. Frontend      -> http://localhost:5173"
Write-Host "  3. AI Brain      -> http://127.0.0.1:8004"
Write-Host "  4. MLflow UI     -> http://127.0.0.1:5001"
Write-Host ""
Write-Host "Stop and close those windows with: .\stop-dev.ps1" -ForegroundColor DarkGray
Write-Host ""
