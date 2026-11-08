[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [securestring]$DatabasePassword,
    [ValidateRange(1, 1440)]
    [int]$StaleAfterMinutes = 10,
    [string]$ComposeFile = "docker-compose.yml"
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$passwordHandle = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($DatabasePassword)
$plainPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($passwordHandle)
try {
    Push-Location $projectRoot
    # Read-only diagnostic: it never modifies ownership or retry state.
    $query = "SELECT task.id AS task_id, task.status, attempt.execution_id, attempt.heartbeat_at, attempt.lease_expires_at FROM analysis_tasks task LEFT JOIN task_execution_attempts attempt ON attempt.id = (SELECT candidate.id FROM task_execution_attempts candidate WHERE candidate.task_id = task.id AND candidate.status IN ('running','retrying') ORDER BY candidate.started_at DESC LIMIT 1) WHERE task.status IN ('running','retrying') AND (attempt.id IS NULL OR attempt.heartbeat_at < now() - interval '$StaleAfterMinutes minutes' OR attempt.lease_expires_at < now()) ORDER BY task.id;"
    docker compose -f $ComposeFile exec -T -e "PGPASSWORD=$plainPassword" postgres psql -U agent_backup -d agent_platform -v ON_ERROR_STOP=1 -c $query
    if ($LASTEXITCODE -ne 0) { throw "Orphaned-task scan failed." }
}
finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordHandle)
    Pop-Location
}
