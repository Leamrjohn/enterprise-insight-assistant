[CmdletBinding()]
param(
    [string]$ComposeFile = "docker-compose.yml"
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Push-Location $projectRoot
try {
    Write-Host "Broker queue depth:"
    foreach ($queue in @("celery", "reports")) {
        $depth = (docker compose -f $ComposeFile exec -T redis redis-cli LLEN $queue).Trim()
        if ($LASTEXITCODE -ne 0 -or $depth -notmatch "^\d+$") { throw "Could not read Redis queue depth for $queue." }
        Write-Host "$queue=$depth"
    }

    Write-Host "Worker queues:"
    docker compose -f $ComposeFile exec -T worker celery -A app.core.celery_app:celery_app inspect active_queues
    if ($LASTEXITCODE -ne 0) { throw "Could not inspect Worker queues." }
    Write-Host "Worker active/reserved/scheduled tasks:"
    foreach ($state in @("active", "reserved", "scheduled")) {
        Write-Host "${state}:"
        docker compose -f $ComposeFile exec -T worker celery -A app.core.celery_app:celery_app inspect $state
        if ($LASTEXITCODE -ne 0) { throw "Could not inspect Worker $state tasks." }
    }

    Write-Host "Durable delivery state:"
    $query = @"
SELECT 'analysis_outbox:' || status || ':' || count(*)
FROM analysis_task_outbox_events GROUP BY status
UNION ALL
SELECT 'analysis_outbox_overdue_broker_accepted:' || count(*)
FROM analysis_task_outbox_events
WHERE status = 'broker_accepted' AND publish_lease_expires_at <= now()
UNION ALL
SELECT 'analysis_tasks_inflight_total:' || count(*)
FROM analysis_tasks
WHERE status IN ('queued', 'running', 'retrying')
UNION ALL
SELECT 'analysis_tasks_inflight_company:' || company_id || ':' || count(*)
FROM analysis_tasks
WHERE status IN ('queued', 'running', 'retrying')
GROUP BY company_id
UNION ALL
SELECT 'analysis_tasks_oldest_pending_seconds:' || COALESCE(
    EXTRACT(EPOCH FROM now() - MIN(created_at))::bigint,
    0
)
FROM analysis_tasks
WHERE status IN ('queued', 'retrying')
UNION ALL
SELECT 'artifact_jobs:' || status || ':' || count(*)
FROM artifact_processing_jobs GROUP BY status
UNION ALL
SELECT 'artifact_outbox:' || status || ':' || count(*)
FROM artifact_processing_outbox_events GROUP BY status
ORDER BY 1;
"@
    docker compose -f $ComposeFile exec -T postgres psql -U agent_backup -d agent_platform -v ON_ERROR_STOP=1 -At -c $query
    if ($LASTEXITCODE -ne 0) { throw "Could not inspect durable queue state." }

}
finally {
    Pop-Location
}
