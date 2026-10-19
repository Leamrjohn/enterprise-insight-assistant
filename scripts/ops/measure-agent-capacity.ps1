[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateNotNullOrEmpty()]
    [string[]]$TaskIds,
    [Parameter(Mandatory)]
    [ValidatePattern("^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")]
    [string]$WorkerContainer,
    [ValidateRange(1, 60)]
    [int]$PollSeconds = 1,
    [ValidateRange(1, 900)]
    [int]$TimeoutSeconds = 300,
    [ValidateRange(0, 900)]
    [int]$WaitForWorkerSeconds = 0,
    [string]$ComposeFile = "docker-compose.yml"
)

$ErrorActionPreference = "Stop"

[int[]]$ParsedTaskIds = @(
    $TaskIds | ForEach-Object { $_ -split "," } | ForEach-Object {
        if ($_ -notmatch "^\d+$") { throw "TaskIds must contain positive integer IDs." }
        [int]$_
    }
)
if ($ParsedTaskIds.Count -eq 0 -or @($ParsedTaskIds | Where-Object { $_ -le 0 }).Count -gt 0) {
    throw "TaskIds must contain positive integer IDs."
}

function Convert-MemoryToBytes([string]$value) {
    $match = [regex]::Match($value, "^\s*([0-9.]+)(B|KiB|MiB|GiB)")
    if (-not $match.Success) { throw "Could not parse Docker memory usage: $value" }
    $multipliers = @{ B = 1; KiB = 1KB; MiB = 1MB; GiB = 1GB }
    return [double]$match.Groups[1].Value * $multipliers[$match.Groups[2].Value]
}

function Get-Percentile([double[]]$Values, [double]$Percentile = 0.95) {
    if ($Values.Count -eq 0) { return $null }
    $ordered = @($Values | Sort-Object)
    $rank = ($ordered.Count - 1) * $Percentile
    $low = [math]::Floor($rank)
    $high = [math]::Ceiling($rank)
    return $ordered[$low] + (($ordered[$high] - $ordered[$low]) * ($rank - $low))
}

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$taskIdSql = ($ParsedTaskIds | Sort-Object -Unique) -join ","
Push-Location $projectRoot
try {
    $workerDeadline = (Get-Date).ToUniversalTime().AddSeconds($WaitForWorkerSeconds)
    do {
        try {
            $running = (docker inspect -f '{{.State.Running}}' $WorkerContainer 2>$null).Trim()
            $inspectExitCode = $LASTEXITCODE
        } catch {
            $running = ""
            $inspectExitCode = 1
        }
        if ($inspectExitCode -eq 0 -and $running -eq "true") { break }
        if ($WaitForWorkerSeconds -eq 0 -or (Get-Date).ToUniversalTime() -ge $workerDeadline) { break }
        Start-Sleep -Milliseconds 200
    } while ($true)
    if ($inspectExitCode -ne 0 -or $running -ne "true") {
        throw "Worker container is not running: $WorkerContainer"
    }
    $workerStartedAt = (docker inspect -f '{{.State.StartedAt}}' $WorkerContainer).Trim()
    if ($LASTEXITCODE -ne 0) { throw "Could not read Worker start time." }

    $terminal = @("completed", "partial", "failed", "cancelled", "needs_clarification")
    $samples = @()
    $deadline = (Get-Date).ToUniversalTime().AddSeconds($TimeoutSeconds)
    do {
        $observedAt = (Get-Date).ToUniversalTime().ToString("o")
        $memory = (docker stats --no-stream --format '{{.MemUsage}}' $WorkerContainer).Trim()
        if ($LASTEXITCODE -ne 0) { throw "Could not read Worker memory usage." }
        $rows = @(docker compose -f $ComposeFile exec -T postgres psql -U postgres -d agent_platform -At -F '|' -c "SELECT id || '|' || status FROM analysis_tasks WHERE id IN ($taskIdSql) ORDER BY id;")
        if ($LASTEXITCODE -ne 0) { throw "Could not read task status." }
        $statusRows = @($rows | Where-Object { $_ -match '^\d+\|' })
        if ($statusRows.Count -ne ($ParsedTaskIds | Sort-Object -Unique).Count) {
            throw "The requested task set is incomplete or inaccessible."
        }
        $samples += [ordered]@{
            observed_at_utc = $observedAt
            memory_bytes = [math]::Round((Convert-MemoryToBytes $memory))
            statuses = @($statusRows)
        }
        $statuses = @($statusRows | ForEach-Object { ($_ -split '\|', 2)[1] })
        $done = @($statuses | Where-Object { $_ -in $terminal }).Count -eq $statuses.Count
        if ($done) { break }
        Start-Sleep -Seconds $PollSeconds
    } while ((Get-Date).ToUniversalTime() -lt $deadline)

    if (-not $done) { throw "Timed out before every requested task reached a terminal state." }
    $summarySql = @"
WITH attempts AS (
  SELECT a.task_id, EXTRACT(EPOCH FROM (a.finished_at - a.started_at)) * 1000 AS duration_ms,
         EXTRACT(EPOCH FROM (a.started_at - TIMESTAMPTZ '$workerStartedAt')) * 1000 AS queue_wait_ms
  FROM task_execution_attempts a WHERE a.task_id IN ($taskIdSql)
), calls AS (
  SELECT billing_status, cost FROM model_call_records WHERE task_id IN ($taskIdSql)
)
SELECT json_build_object(
  'worker_started_at_utc', '$workerStartedAt',
  'attempt_duration_p95_ms', (SELECT percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_ms) FROM attempts),
  'queue_wait_p95_ms', (SELECT percentile_cont(0.95) WITHIN GROUP (ORDER BY queue_wait_ms) FROM attempts),
  'settled_cost', (SELECT COALESCE(sum(cost), 0) FROM calls WHERE billing_status = 'settled'),
  'unknown_calls', (SELECT count(*) FROM calls WHERE billing_status = 'unknown')
);
"@
    $databaseSummary = (docker compose -f $ComposeFile exec -T postgres psql -U postgres -d agent_platform -At -c $summarySql).Trim()
    if ($LASTEXITCODE -ne 0) { throw "Could not read terminal metrics." }
    $memory = @($samples | ForEach-Object { [double]$_.memory_bytes })
    [ordered]@{
        schema_version = "agent-capacity-measurement/v1"
        task_ids = @($ParsedTaskIds | Sort-Object -Unique)
        worker_container = $WorkerContainer
        sample_count = $samples.Count
        memory_p95_bytes = [math]::Round((Get-Percentile $memory))
        memory_peak_bytes = [math]::Round(($memory | Measure-Object -Maximum).Maximum)
        samples = $samples
        database_summary = ($databaseSummary | ConvertFrom-Json)
    } | ConvertTo-Json -Depth 6
} finally {
    Pop-Location
}
