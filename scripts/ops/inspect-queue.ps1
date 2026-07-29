[CmdletBinding()]
param(
    [ValidateRange(1, 500)]
    [int]$LogLines = 100,
    [ValidateRange(1, 1000)]
    [int]$MaxKeys = 100,
    [string]$ComposeFile = "docker-compose.yml"
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Push-Location $projectRoot
try {
    Write-Host "Redis keys (names only):"
    $queueKeys = @(docker compose -f $ComposeFile exec -T redis redis-cli --scan --pattern "celery*")
    $queueKeys | Select-Object -First $MaxKeys
    Write-Host "Recent Worker logs:"
    docker compose -f $ComposeFile logs --tail $LogLines worker report-worker
}
finally {
    Pop-Location
}
