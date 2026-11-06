$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false

$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $projectRoot
try {
    $envPath = Join-Path $projectRoot '.env'
    if (-not (Test-Path -LiteralPath $envPath)) {
        Copy-Item -LiteralPath '.env.example' -Destination $envPath
    }

    $envText = [IO.File]::ReadAllText($envPath)
    $originalEnvText = $envText
    foreach ($key in 'STUDYHUB_PROCESSING_TOKEN', 'STUDYHUB_SEARCH_TOKEN', 'STUDYHUB_SYNTHESIS_TOKEN') {
        $assignment = "(?m)^[ \t]*${key}[ \t]*="
        $emptyAssignment = $assignment + '[ \t]*(?=\r?$)'
        if ($envText -match $emptyAssignment) {
            $token = [guid]::NewGuid().ToString('N')
            $envText = [regex]::Replace($envText, $emptyAssignment, "$key=$token")
        } elseif ($envText -notmatch $assignment) {
            $token = [guid]::NewGuid().ToString('N')
            $envText = $envText.TrimEnd() + "`r`n$key=$token`r`n"
        }
    }
    if ($envText -ne $originalEnvText) {
        [IO.File]::WriteAllText($envPath, $envText, [Text.UTF8Encoding]::new($false))
    }

    $python = Join-Path $projectRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $python)) {
        & py -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python virtual environment.' }
    }

    Write-Host 'Installing Python requirements...'
    & $python -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Could not install Python requirements.' }

    $composeJson = & docker compose config --format json
    if ($LASTEXITCODE -ne 0) { throw 'Could not read compose.yaml. Check Docker and .env.' }
    $database = ($composeJson | Out-String | ConvertFrom-Json).services.db.environment
    $dbUser = $database.POSTGRES_USER
    $dbName = $database.POSTGRES_DB

    Write-Host 'Starting PostgreSQL and RabbitMQ...'
    & docker compose up -d db rabbitmq
    if ($LASTEXITCODE -ne 0) { throw 'Could not start PostgreSQL and RabbitMQ. Check Docker Desktop.' }

    $dbReady = $false
    for ($attempt = 1; $attempt -le 30; $attempt++) {
        & docker compose exec -T db pg_isready -q -t 1 -h 127.0.0.1 -U $dbUser -d $dbName
        if ($LASTEXITCODE -eq 0) {
            $dbReady = $true
            break
        }
        Start-Sleep -Seconds 2
    }
    if (-not $dbReady) { throw 'PostgreSQL did not become ready. Check docker compose logs db.' }

    $migrations = @(Get-ChildItem -LiteralPath '.\migrations' -Filter '*.sql' -File | Sort-Object Name)
    if ($migrations.Count -eq 0) { throw 'No SQL migrations were found.' }

    foreach ($migration in $migrations) {
        Write-Host "Applying $($migration.Name)..."
        Get-Content -Raw -LiteralPath $migration.FullName |
            & docker compose exec -T db psql -v ON_ERROR_STOP=1 -U $dbUser -d $dbName
        if ($LASTEXITCODE -ne 0) { throw "Migration failed: $($migration.Name)" }
    }


    Write-Host 'Setup complete. Run .\setup\start-content-service.ps1 to start the API and Relay.'
} finally {
    Pop-Location
}
