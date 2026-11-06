$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$relay = $null

$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $projectRoot
try {
    $python = Join-Path $projectRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath '.env') -or -not (Test-Path -LiteralPath $python)) {
        throw 'Run .\setup\setup-content-service.ps1 first.'
    }

    & docker compose up -d db rabbitmq
    if ($LASTEXITCODE -ne 0) { throw 'Could not start PostgreSQL and RabbitMQ. Check Docker Desktop.' }

    $dbReady = $false
    for ($attempt = 1; $attempt -le 30; $attempt++) {
        & docker compose exec -T db pg_isready -q -t 1 -h 127.0.0.1
        if ($LASTEXITCODE -eq 0) {
            $dbReady = $true
            break
        }
        Start-Sleep -Seconds 2
    }
    if (-not $dbReady) { throw 'PostgreSQL did not become ready. Check docker compose logs db.' }

    $relayLog = Join-Path $projectRoot '.venv\relay.log'
    $relayErrors = Join-Path $projectRoot '.venv\relay-errors.log'
    $relayOptions = @{
        FilePath = $python
        ArgumentList = @('-u', 'relay.py')
        WorkingDirectory = $projectRoot
        WindowStyle = 'Hidden'
        PassThru = $true
        RedirectStandardOutput = $relayLog
        RedirectStandardError = $relayErrors
    }
    $relay = Start-Process @relayOptions

    Write-Host 'Waiting for Relay to connect to RabbitMQ...'
    $relayReady = $false
    for ($attempt = 1; $attempt -le 60; $attempt++) {
        if ($relay.HasExited) { break }
        if (Select-String -LiteralPath $relayLog -Pattern '^Relay ready$' -Quiet) {
            $relayReady = $true
            break
        }
        Start-Sleep -Seconds 1
    }
    if (-not $relayReady) { throw "Relay did not become ready. Check $relayLog and $relayErrors." }

    Write-Host 'Open http://127.0.0.1:8000/docs to test the API.'
    Write-Host 'Press Ctrl+C to stop the API and Relay.'
    Write-Host "Relay output: $relayLog"
    & $python -m uvicorn main:app
    if ($LASTEXITCODE -ne 0) { throw 'The API stopped with an error.' }
} finally {
    if ($null -ne $relay -and -not $relay.HasExited) {
        # The Windows venv launcher may have started a child Python process.
        & taskkill.exe /PID $relay.Id /T /F 2>$null | Out-Null
    }
    Pop-Location
}
