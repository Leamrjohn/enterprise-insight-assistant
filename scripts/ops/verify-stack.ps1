[CmdletBinding()]
param(
    [string]$ComposeFile = "docker-compose.yml"
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path

function Invoke-ComposeCheck {
    param(
        [string[]]$ComposeArguments,
        [string]$FailureMessage
    )

    & docker compose -f $ComposeFile @ComposeArguments
    if ($LASTEXITCODE -ne 0) {
        throw $FailureMessage
    }
}

Push-Location $projectRoot
try {
    Invoke-ComposeCheck -ComposeArguments @("config", "--quiet") -FailureMessage "Compose configuration is invalid."
    Invoke-ComposeCheck -ComposeArguments @("ps") -FailureMessage "Compose services could not be listed."
    Invoke-ComposeCheck -ComposeArguments @("exec", "-T", "postgres", "pg_isready", "-U", "agent_app", "-d", "agent_platform") -FailureMessage "PostgreSQL is not ready."
    Invoke-ComposeCheck -ComposeArguments @("exec", "-T", "redis", "redis-cli", "ping") -FailureMessage "Redis is not ready."
    Invoke-ComposeCheck -ComposeArguments @("exec", "-T", "capacity-signal", "python", "-c", "from urllib.request import urlopen; assert urlopen('http://127.0.0.1:8081/health/live', timeout=1).status == 200") -FailureMessage "Capacity signal is not live."
    Invoke-ComposeCheck -ComposeArguments @("exec", "-T", "localstack", "awslocal", "s3api", "head-bucket", "--bucket", "agent-artifacts") -FailureMessage "Object storage bucket is not ready."
    Invoke-ComposeCheck -ComposeArguments @("exec", "-T", "api", "alembic", "current") -FailureMessage "Alembic revision cannot be read from the API image."
    Invoke-ComposeCheck -ComposeArguments @("exec", "-T", "api", "python", "-c", "from app.core.settings import get_settings; from app.modules.workflow.capacity import require_task_capacity; require_task_capacity(get_settings())") -FailureMessage "Task capacity admission is not ready."
    Invoke-ComposeCheck -ComposeArguments @("exec", "-T", "worker", "celery", "-A", "app.core.celery_app:celery_app", "inspect", "ping") -FailureMessage "No Celery Worker replied to the control ping."
    $response = Invoke-WebRequest -UseBasicParsing "http://localhost:8000/health/ready"
    if ($response.StatusCode -ne 200) {
        throw "API readiness returned HTTP $($response.StatusCode)."
    }
    Write-Host "Stack verification passed."
}
finally {
    Pop-Location
}
