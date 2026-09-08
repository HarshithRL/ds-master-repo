# Mate local dev — stop Flask :5000, Vite :5173, MLflow :5001, AI Brain :8004
# and close the PowerShell windows opened by start-dev.ps1
# Usage (from repo root): .\stop-dev.ps1

$ErrorActionPreference = "Continue"

$RepoRoot = $PSScriptRoot
$PidFile = Join-Path $RepoRoot ".mate-dev.pids"

$DevPorts = @(
    @{ Port = 5000; Label = "Flask API" },
    @{ Port = 5173; Label = "Vite frontend" },
    @{ Port = 5001; Label = "MLflow UI" },
    @{ Port = 8004; Label = "AI Brain" }
)

function Get-PortListenerPids {
    param([int]$Port)

    $pids = [System.Collections.Generic.HashSet[int]]::new()

    try {
        $connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop
        foreach ($conn in $connections) {
            if ($conn.OwningProcess -gt 0) {
                [void]$pids.Add([int]$conn.OwningProcess)
            }
        }
    }
    catch {
        $pattern = ":$Port\s"
        $lines = netstat -ano | Select-String "LISTENING" | Select-String $pattern
        foreach ($line in $lines) {
            $parts = ($line -split "\s+") | Where-Object { $_ -ne "" }
            if ($parts.Count -ge 1) {
                $procId = [int]$parts[-1]
                if ($procId -gt 0) {
                    [void]$pids.Add($procId)
                }
            }
        }
    }

    return @($pids)
}

function Get-ProcessSummary {
    param([int]$ProcId)

    try {
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcId" -ErrorAction Stop
        $cmd = $proc.CommandLine
        if (-not $cmd) {
            $cmd = $proc.Name
        }
        if ($cmd.Length -gt 120) {
            $cmd = $cmd.Substring(0, 117) + "..."
        }
        return $cmd
    }
    catch {
        return "(process $ProcId)"
    }
}

function Stop-Listener {
    param(
        [int]$ProcId,
        [string]$Label
    )

    $summary = Get-ProcessSummary -ProcId $ProcId
    Write-Host "  Stopping PID $ProcId ($Label): $summary" -ForegroundColor Yellow
    $null = taskkill /F /PID $ProcId /T 2>&1
}

function Get-MateShellPids {
    $found = [System.Collections.Generic.HashSet[int]]::new()

    if (Test-Path $PidFile) {
        foreach ($line in Get-Content $PidFile) {
            $trimmed = $line.Trim()
            if ($trimmed -match '^\d+$') {
                [void]$found.Add([int]$trimmed)
            }
        }
    }

    Get-Process -Name powershell, pwsh -ErrorAction SilentlyContinue | ForEach-Object {
        if ($_.MainWindowTitle -like 'Mate *') {
            [void]$found.Add([int]$_.Id)
        }
    }

    Get-CimInstance Win32_Process -Filter "Name='powershell.exe' OR Name='pwsh.exe'" -ErrorAction SilentlyContinue |
        ForEach-Object {
            $cmd = $_.CommandLine
            if ($cmd -and ($cmd -match "WindowTitle = 'Mate " -or $cmd -match "Mate \d/4")) {
                [void]$found.Add([int]$_.ProcessId)
            }
        }

    [void]$found.Remove([int]$PID)
    return @($found | Where-Object { $_ -gt 0 })
}

Write-Host ""
Write-Host "=== Mate stop-dev ===" -ForegroundColor Cyan
Write-Host "Targets: :5000 Flask, :5173 Vite, :5001 MLflow, :8004 AI Brain" -ForegroundColor DarkGray
Write-Host ""

$targets = @{}
foreach ($entry in $DevPorts) {
    foreach ($procId in (Get-PortListenerPids -Port $entry.Port)) {
        if (-not $targets.ContainsKey($procId)) {
            $targets[$procId] = $entry.Label
        }
    }
}

if ($targets.Count -gt 0) {
    Write-Host "Found $($targets.Count) listener process(es):" -ForegroundColor White
    foreach ($kv in $targets.GetEnumerator() | Sort-Object Name) {
        Stop-Listener -ProcId $kv.Key -Label $kv.Value
    }
}
else {
    Write-Host "No listeners on ports 5000, 5173, 5001, or 8004." -ForegroundColor DarkGray
}

$shellPids = @(Get-MateShellPids)
if ($shellPids.Count -gt 0) {
    Write-Host ""
    Write-Host "Closing $($shellPids.Count) Mate terminal window(s):" -ForegroundColor White
    foreach ($procId in ($shellPids | Sort-Object)) {
        if ($targets.ContainsKey($procId)) {
            continue
        }
        Stop-Listener -ProcId $procId -Label "Mate terminal"
    }
}

if (Test-Path $PidFile) {
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
}

Start-Sleep -Seconds 2

Write-Host ""
Write-Host "Port check:" -ForegroundColor Cyan
$stillListening = $false
foreach ($entry in $DevPorts) {
    $remaining = Get-PortListenerPids -Port $entry.Port
    if ($remaining.Count -gt 0) {
        $stillListening = $true
        Write-Host "  :$($entry.Port) still listening (PID $($remaining -join ', '))" -ForegroundColor Red
    }
    else {
        Write-Host "  :$($entry.Port) free ($($entry.Label))" -ForegroundColor Green
    }
}

$leftoverShells = @(Get-MateShellPids)
if ($leftoverShells.Count -gt 0) {
    Write-Host "  Mate windows still open (PID $($leftoverShells -join ', '))" -ForegroundColor Yellow
}

if ($stillListening) {
    Write-Host ""
    Write-Host "Some ports are still in use. Run stop-dev again." -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "All Mate dev ports stopped and terminal windows closed." -ForegroundColor Green
Write-Host "Restart with: .\start-dev.ps1" -ForegroundColor DarkGray
Write-Host ""
