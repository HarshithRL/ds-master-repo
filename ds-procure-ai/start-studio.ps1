# Start local LangGraph Studio without changing application processes on :8004.
$ErrorActionPreference = "Stop"
$RepoRoot = $PSScriptRoot
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$Cli = Join-Path $RepoRoot ".venv\Scripts\langgraph.exe"
$EnvFile = Join-Path $RepoRoot ".env.studio"

if (-not (Test-Path $Python)) {
    throw "Python venv not found. Create it, then run: .\.venv\Scripts\python.exe -m pip install -r requirements-studio.txt"
}
if (-not (Test-Path $Cli)) {
    throw "LangGraph Studio CLI is not installed. Run: .\.venv\Scripts\python.exe -m pip install -r requirements-studio.txt"
}
if (-not (Test-Path $EnvFile)) {
    throw "Create .env.studio from .env.studio.example, then run .\scripts\seed_studio_data.py before starting Studio."
}

Set-Location $RepoRoot
& $Cli dev --host 127.0.0.1 --port 2024 --allow-blocking
