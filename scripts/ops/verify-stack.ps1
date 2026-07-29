[CmdletBinding()]
param(
    [string]$ComposeFile = "docker-compose.yml"
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Push-Location $projectRoot
try {
    docker compose -f $ComposeFile config --quiet
    docker compose -f $ComposeFile ps
    docker compose -f $ComposeFile exec -T postgres pg_isready -U agent_app -d agent_platform
    docker compose -f $ComposeFile exec -T redis redis-cli ping
    $response = Invoke-WebRequest -UseBasicParsing "http://localhost:8000/health/ready"
    if ($response.StatusCode -ne 200) {
        throw "API readiness returned HTTP $($response.StatusCode)."
    }
    Write-Host "Stack verification passed."
}
finally {
    Pop-Location
}
