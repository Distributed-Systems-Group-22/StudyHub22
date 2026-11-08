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

    foreach ($pair in @(
        @{ Key = 'SYNTHESIS_DB'; Val = 'synthesis_db' },
        @{ Key = 'SYNTHESIS_DB_USER'; Val = 'synthesis' },
        @{ Key = 'SYNTHESIS_DB_PASSWORD'; Val = 'synthesis_dev' },
        @{ Key = 'OLLAMA_BASE_URL'; Val = 'http://host.docker.internal:11434' },
        @{ Key = 'AI_MODEL'; Val = 'llama3.2:1b' }
    )) {
        $k = $pair.Key
        $v = $pair.Val
        $assignment = "(?m)^[ \t]*${k}[ \t]*="
        if ($envText -notmatch $assignment) {
            $envText = $envText.TrimEnd() + "`r`n$k=$v`r`n"
        }
    }
    if ($envText -ne $originalEnvText) {
        [IO.File]::WriteAllText($envPath, $envText, [Text.UTF8Encoding]::new($false))
    }

    Write-Host 'Configuration ready. Run docker compose up --build -d.'
} finally {
    Pop-Location
}
