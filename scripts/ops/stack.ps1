[CmdletBinding(SupportsShouldProcess)]
param([Parameter(Mandatory)][ValidateSet('up', 'down', 'status')][string]$Mode)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$services = @('postgres', 'business_db', 'demo_business_acme', 'demo_business_beta',
    'redis', 'clamd', 'localstack', 'capacity-signal', 'api', 'worker',
    'report-worker', 'beat', 'frontend')
$rows = @(& docker ps -a --filter 'label=com.docker.compose.project=agent' --format '{{.Names}}|{{.Label "com.docker.compose.service"}}|{{.State}}|{{.Label "com.docker.compose.project.working_dir"}}')
if ($LASTEXITCODE -ne 0) { throw 'Cannot list project containers.' }
$containers = @{}
foreach ($row in $rows) {
    $parts = $row -split '\|', 4
    if ($parts.Count -ne 4) { throw 'Unexpected Docker output.' }
    if ($parts[1] -notin $services) { continue }
    if (-not $parts[0].StartsWith('agent-') -or $parts[3] -ne $projectRoot) {
        throw "Container ownership mismatch: $($parts[0])"
    }
    if ($containers.ContainsKey($parts[1])) { throw "Duplicate service: $($parts[1])" }
    $containers[$parts[1]] = @{ Name = $parts[0]; State = $parts[2] }
}
# Missing containers require a reviewed bootstrap; never implicitly run migrations or seeds.
foreach ($service in $services) {
    if (-not $containers.ContainsKey($service)) { throw "Missing container for $service; bootstrap requires review." }
}
if ($Mode -eq 'down') { [array]::Reverse($services) }
if ($Mode -ne 'status') {
    foreach ($service in $services) {
        $container = $containers[$service]
        if ($Mode -eq 'up' -and $container.State -eq 'running') { continue }
        if ($Mode -eq 'down' -and $container.State -eq 'exited') { continue }
        if ($PSCmdlet.ShouldProcess($container.Name, $Mode)) {
            if ($Mode -eq 'up') { & docker start $container.Name }
            else { & docker stop --timeout 30 $container.Name }
            if ($LASTEXITCODE -ne 0) { throw "Failed to $Mode $($container.Name)" }
        }
    }
    if ($WhatIfPreference) { return }
}
$names = @($services | ForEach-Object { $containers[$_].Name })
$deadline = [DateTime]::UtcNow.AddSeconds(120)
do {
    $states = @(& docker inspect --format '{{.Name}}|{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' @names)
    if ($LASTEXITCODE -ne 0 -or $states.Count -ne $names.Count) { throw 'Cannot inspect all project containers.' }
    $bad = @($states | Where-Object {
        $parts = $_ -split '\|'
        if ($Mode -eq 'down') { $parts[1] -ne 'exited' }
        else { $parts[1] -ne 'running' -or $parts[2] -notin @('none', 'healthy') }
    })
    $ready = $false
    if ($Mode -ne 'down') {
        try {
            $response = Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:8000/health/ready' -TimeoutSec 5
            $ready = $response.StatusCode -eq 200 -and ($response.Content | ConvertFrom-Json).status -eq 'ok'
        } catch { $ready = $false }
    }
    if ($Mode -ne 'up' -or ($bad.Count -eq 0 -and $ready)) { break }
    Start-Sleep -Seconds 2
} while ([DateTime]::UtcNow -lt $deadline)
$states | Write-Output
if ($Mode -ne 'down') { Write-Output "API readiness: $ready" }
if ($bad.Count -gt 0 -or ($Mode -ne 'down' -and -not $ready)) { throw "Stack $Mode validation failed." }
