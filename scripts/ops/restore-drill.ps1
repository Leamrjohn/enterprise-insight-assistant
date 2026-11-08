[CmdletBinding(SupportsShouldProcess, ConfirmImpact = "High")]
param(
    [Parameter(Mandatory)]
    [ValidateScript({ Test-Path $_ -PathType Leaf })]
    [string]$BackupPath,
    [ValidatePattern("^[A-Za-z0-9_]+$")]
    [string]$TargetDatabase = "agent_platform_restore_drill",
    [Parameter(Mandatory)]
    [securestring]$DatabasePassword,
    [ValidatePattern("^[A-Za-z0-9_]+$")]
    [string]$DatabaseAdminUser = "agent_restore",
    [ValidateRange(1, 1440)]
    [int]$MaxBackupAgeMinutes = 15,
    [ValidateRange(1, 3600)]
    [int]$MaxRestoreSeconds = 900,
    [string]$ComposeFile = "docker-compose.yml"
)

$ErrorActionPreference = "Stop"
if ($TargetDatabase -in @("agent_platform", "agent_platform_test")) {
    throw "Restore drill may not target an application database."
}
if (-not $TargetDatabase.StartsWith("agent_platform_restore_")) {
    throw "Restore drill target must begin with agent_platform_restore_."
}
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$resolvedBackup = (Resolve-Path $BackupPath).Path
$manifestPath = "$resolvedBackup.manifest.json"
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    throw "Backup manifest is missing: $manifestPath"
}
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
if ($manifest.schema_version -ne "postgres-backup-manifest/v1") {
    throw "Unsupported backup manifest schema."
}
if ($manifest.dump_file -ne [System.IO.Path]::GetFileName($resolvedBackup)) {
    throw "Backup manifest does not belong to the requested dump."
}
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $resolvedBackup).Hash -ne $manifest.dump_sha256) {
    throw "Backup checksum does not match its manifest."
}
$backupAge = (New-TimeSpan -Start ([datetimeoffset]$manifest.created_at_utc).UtcDateTime -End (Get-Date).ToUniversalTime())
if ($backupAge.TotalMinutes -gt $MaxBackupAgeMinutes) {
    throw "Backup age $([math]::Round($backupAge.TotalMinutes, 2)) minutes exceeds the accepted RPO of $MaxBackupAgeMinutes minutes."
}
$passwordHandle = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($DatabasePassword)
$plainPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($passwordHandle)

if ($PSCmdlet.ShouldProcess($TargetDatabase, "replace restore-drill database")) {
    Push-Location $projectRoot
    try {
        $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
        $containerId = (docker compose -f $ComposeFile ps -q postgres).Trim()
        if (-not $containerId) { throw "PostgreSQL container is not running." }
        docker cp $resolvedBackup "${containerId}:/tmp/restore-drill.dump"
        docker compose -f $ComposeFile exec -T -e "PGPASSWORD=$plainPassword" postgres dropdb -U $DatabaseAdminUser --if-exists $TargetDatabase
        if ($LASTEXITCODE -ne 0) { throw "Dropping a prior restore-drill database failed." }
        docker compose -f $ComposeFile exec -T -e "PGPASSWORD=$plainPassword" postgres createdb -U $DatabaseAdminUser $TargetDatabase
        if ($LASTEXITCODE -ne 0) { throw "Creating the isolated restore-drill database failed." }
        # The target inherits pgvector from template1. Its extension comment is
        # owned by the template superuser, so restore only application objects.
        docker compose -f $ComposeFile exec -T -e "PGPASSWORD=$plainPassword" postgres pg_restore -U $DatabaseAdminUser -d $TargetDatabase --no-owner --no-comments --exit-on-error /tmp/restore-drill.dump
        if ($LASTEXITCODE -ne 0) { throw "Restoring the backup failed." }
        $restoredAlembicVersion = (docker compose -f $ComposeFile exec -T -e "PGPASSWORD=$plainPassword" postgres psql -U $DatabaseAdminUser -d $TargetDatabase -At -c "SELECT version_num FROM alembic_version ORDER BY version_num LIMIT 1;").Trim()
        if ($LASTEXITCODE -ne 0 -or $restoredAlembicVersion -ne $manifest.alembic_version) { throw "Restored Alembic version does not match the backup manifest." }
        $restoredTableCount = (docker compose -f $ComposeFile exec -T -e "PGPASSWORD=$plainPassword" postgres psql -U $DatabaseAdminUser -d $TargetDatabase -At -c "SELECT count(*) FROM pg_tables WHERE schemaname = 'public';").Trim()
        if ($LASTEXITCODE -ne 0 -or [int64]$restoredTableCount -ne [int64]$manifest.public_table_count) { throw "Restored public table count does not match the backup manifest." }
        foreach ($property in $manifest.critical_table_counts.PSObject.Properties) {
            $table = $property.Name
            $restoredCount = (docker compose -f $ComposeFile exec -T -e "PGPASSWORD=$plainPassword" postgres psql -U $DatabaseAdminUser -d $TargetDatabase -At -c "SELECT count(*) FROM public.$table;").Trim()
            if ($LASTEXITCODE -ne 0 -or [int64]$restoredCount -ne [int64]$property.Value) { throw "Restored row count for $table does not match the backup manifest." }
        }
        docker compose -f $ComposeFile exec -T postgres rm -f /tmp/restore-drill.dump
        if ($LASTEXITCODE -ne 0) { throw "Restore drill completed but temporary dump cleanup failed." }
        $stopwatch.Stop()
        if ($stopwatch.Elapsed.TotalSeconds -gt $MaxRestoreSeconds) { throw "Restore time $([math]::Round($stopwatch.Elapsed.TotalSeconds, 2)) seconds exceeds the accepted RTO of $MaxRestoreSeconds seconds." }
        Write-Host "Restore drill completed in $TargetDatabase in $([math]::Round($stopwatch.Elapsed.TotalSeconds, 2)) seconds; backup age $([math]::Round($backupAge.TotalMinutes, 2)) minutes."
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordHandle)
        Pop-Location
    }
}
