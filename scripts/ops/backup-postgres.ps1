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
$manifestPath = "$hostDump.manifest.json"
$passwordHandle = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($DatabasePassword)
$plainPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($passwordHandle)
$criticalTables = @(
    "analysis_tasks",
    "task_execution_attempts",
    "workflow_checkpoints",
    "workflow_events",
    "analysis_task_outbox_events",
    "model_call_records"
)

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

    $alembicVersion = (docker compose -f $ComposeFile exec -T -e "PGPASSWORD=$plainPassword" postgres psql -U agent_backup -d $Database -At -c "SELECT version_num FROM alembic_version ORDER BY version_num LIMIT 1;").Trim()
    if ($LASTEXITCODE -ne 0 -or -not $alembicVersion) { throw "Could not read the source Alembic version." }
    $publicTableCount = (docker compose -f $ComposeFile exec -T -e "PGPASSWORD=$plainPassword" postgres psql -U agent_backup -d $Database -At -c "SELECT count(*) FROM pg_tables WHERE schemaname = 'public';").Trim()
    if ($LASTEXITCODE -ne 0 -or $publicTableCount -notmatch "^\d+$") { throw "Could not count source public tables." }
    $criticalTableCounts = [ordered]@{}
    foreach ($table in $criticalTables) {
        $count = (docker compose -f $ComposeFile exec -T -e "PGPASSWORD=$plainPassword" postgres psql -U agent_backup -d $Database -At -c "SELECT count(*) FROM public.$table;").Trim()
        if ($LASTEXITCODE -ne 0 -or $count -notmatch "^\d+$") { throw "Could not count source table $table." }
        $criticalTableCounts[$table] = [int64]$count
    }
    $manifest = [ordered]@{
        schema_version = "postgres-backup-manifest/v1"
        created_at_utc = (Get-Date).ToUniversalTime().ToString("o")
        database = $Database
        dump_file = [System.IO.Path]::GetFileName($hostDump)
        dump_bytes = (Get-Item -LiteralPath $hostDump).Length
        dump_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $hostDump).Hash
        alembic_version = $alembicVersion
        public_table_count = [int64]$publicTableCount
        critical_table_counts = $criticalTableCounts
    }
    $manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $manifestPath -Encoding utf8NoBOM
    Write-Host "Backup created: $hostDump"
    Write-Host "Backup manifest: $manifestPath"
}
finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordHandle)
    Pop-Location
}
