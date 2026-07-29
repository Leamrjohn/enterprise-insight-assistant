[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$OutputDirectory,
    [Parameter(Mandatory)]
    [securestring]$DatabasePassword,
    [ValidatePattern("^[A-Za-z0-9_]+$")]
    [string]$Database = "agent_platform",
    [string]$ComposeFile = "docker-compose.yml"
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$resolvedOutput = [System.IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Force -Path $resolvedOutput | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$containerDump = "/tmp/$Database`_$stamp.dump"
$hostDump = Join-Path $resolvedOutput "$Database`_$stamp.dump"
$passwordHandle = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($DatabasePassword)
$plainPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($passwordHandle)

Push-Location $projectRoot
try {
    # The backup role has read-only + BYPASSRLS access. Normal application and
    # migrator identities remain subject to RLS and must not be used here.
    docker compose -f $ComposeFile exec -T -e "PGPASSWORD=$plainPassword" postgres pg_dump -U agent_backup -Fc --no-owner --no-acl -d $Database -f $containerDump
    if ($LASTEXITCODE -ne 0) { throw "pg_dump failed; no backup was created." }
    $containerId = (docker compose -f $ComposeFile ps -q postgres).Trim()
    if (-not $containerId) { throw "PostgreSQL container is not running." }
    docker cp "${containerId}:$containerDump" $hostDump
    if ($LASTEXITCODE -ne 0) { throw "Copying the PostgreSQL backup to the host failed." }
    docker compose -f $ComposeFile exec -T postgres rm -f $containerDump
    if ($LASTEXITCODE -ne 0) { throw "Backup was copied, but temporary container cleanup failed." }
    if ((Get-Item -LiteralPath $hostDump).Length -eq 0) { throw "Backup file is empty." }
    Write-Host "Backup created: $hostDump"
}
finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordHandle)
    Pop-Location
}
