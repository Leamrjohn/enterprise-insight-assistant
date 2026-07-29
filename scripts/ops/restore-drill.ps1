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
    [string]$ComposeFile = "docker-compose.yml"
)

$ErrorActionPreference = "Stop"
if ($TargetDatabase -in @("agent_platform", "agent_platform_test")) {
    throw "Restore drill may not target an application database."
}
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$resolvedBackup = (Resolve-Path $BackupPath).Path
$passwordHandle = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($DatabasePassword)
$plainPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($passwordHandle)

if ($PSCmdlet.ShouldProcess($TargetDatabase, "replace restore-drill database")) {
    Push-Location $projectRoot
    try {
        $containerId = (docker compose -f $ComposeFile ps -q postgres).Trim()
        if (-not $containerId) { throw "PostgreSQL container is not running." }
        docker cp $resolvedBackup "${containerId}:/tmp/restore-drill.dump"
        docker compose -f $ComposeFile exec -T -e "PGPASSWORD=$plainPassword" postgres dropdb -U $DatabaseAdminUser --if-exists $TargetDatabase
        if ($LASTEXITCODE -ne 0) { throw "Dropping a prior restore-drill database failed." }
        docker compose -f $ComposeFile exec -T -e "PGPASSWORD=$plainPassword" postgres createdb -U $DatabaseAdminUser $TargetDatabase
        if ($LASTEXITCODE -ne 0) { throw "Creating the isolated restore-drill database failed." }
        # The target inherits pgvector from template1. Its extension comment is
        # owned by the template superuser, so restore only application objects.
        docker compose -f $ComposeFile exec -T -e "PGPASSWORD=$plainPassword" postgres pg_restore -U $DatabaseAdminUser -d $TargetDatabase --no-owner --no-comments /tmp/restore-drill.dump
        if ($LASTEXITCODE -ne 0) { throw "Restoring the backup failed." }
        docker compose -f $ComposeFile exec -T -e "PGPASSWORD=$plainPassword" postgres psql -U $DatabaseAdminUser -d $TargetDatabase -c "SELECT count(*) AS restored_tables FROM pg_tables WHERE schemaname = 'public';"
        if ($LASTEXITCODE -ne 0) { throw "Validating the restored database failed." }
        docker compose -f $ComposeFile exec -T postgres rm -f /tmp/restore-drill.dump
        if ($LASTEXITCODE -ne 0) { throw "Restore drill completed but temporary dump cleanup failed." }
        Write-Host "Restore drill completed in $TargetDatabase."
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordHandle)
        Pop-Location
    }
}
