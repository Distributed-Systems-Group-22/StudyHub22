$ErrorActionPreference = 'Stop'
Push-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
try {
    if (-not (Test-Path -LiteralPath '.env')) { throw 'Run setup/setup-content-service.ps1 first.' }
    & docker compose up --build -d
    if ($LASTEXITCODE -ne 0) { throw 'Compose startup failed. Check Docker Desktop and docker compose logs.' }
    Write-Host 'API: http://127.0.0.1:8000/docs'
    Write-Host 'Logs: docker compose logs -f content-api content-relay'
    Write-Host 'Stop: docker compose down'
} finally {
    Pop-Location
}
