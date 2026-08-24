# Start the RTG Forecast app (PowerShell).
#   .\run.ps1                 -> live IFS data (falls back to snapshot until you Connect IFS)
#   .\run.ps1 snapshot        -> offline snapshot data only
#   .\run.ps1 live 8001       -> override the app port (default 8000)
param(
    [string]$Mode = "live",
    [int]$Port = 8000
)
Set-Location -Path $PSScriptRoot

$py = ".\.venv\Scripts\python.exe"

Write-Host "[run] applying DB migrations (idempotent)..."
& $py -m alembic upgrade head 2>$null
if ($LASTEXITCODE -ne 0) { Write-Host "[run] alembic skipped (create_all will cover it)" }

Write-Host "[run] starting app  mode=$Mode  port=$Port  (OAuth callback -> http://localhost:$Port/callback)"
$env:RTG_DATA_SOURCE = $Mode
$env:RTG_APP_PORT = "$Port"
& $py -m uvicorn app.main:app --reload --port $Port
