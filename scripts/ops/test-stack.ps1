$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$services = @('postgres', 'business_db', 'demo_business_acme', 'demo_business_beta',
    'redis', 'clamd', 'localstack', 'capacity-signal', 'api', 'worker',
    'report-worker', 'beat', 'frontend')
$mock = @{ State = 'running'; Scenario = 'normal'; Calls = @() }
function docker {
    $global:LASTEXITCODE = 0
    if ($args[0] -eq 'ps') {
        foreach ($service in $services) {
            if ($mock.Scenario -eq 'missing' -and $service -eq 'api') { continue }
            $name = "agent-$service-1"
            if ($mock.Scenario -eq 'foreign' -and $service -eq 'api') { $name = 'foreign-api' }
            "$name|$service|$($mock.State)|$root"
        }
        "agent-migrate-1|migrate|exited|$root"
        "agent-seed-1|demo_seed_acme|exited|$root"
    } elseif ($args[0] -eq 'inspect') {
        foreach ($service in $services) { "/agent-$service-1|$($mock.State)|none" }
    } elseif ($args[0] -in @('start', 'stop')) {
        $mock.Calls += ,@($args)
        if ($mock.Scenario -eq 'docker-failure') { $global:LASTEXITCODE = 1; return }
        $mock.State = if ($args[0] -eq 'start') { 'running' } else { 'exited' }
    } else { throw 'Unexpected Docker command in self-check.' }
}
function Invoke-WebRequest {
    if ($mock.Scenario -eq 'api-failure') { throw 'API unavailable' }
    @{ StatusCode = 200; Content = '{"status":"ok"}' }
}
function Assert-Rejected([string]$Scenario, [string]$Expected, [string]$Mode = 'status') {
    $mock.Scenario = $Scenario
    $rejected = $false
    try { & "$PSScriptRoot/stack.ps1" -Mode $Mode | Out-Null }
    catch { if ($_.Exception.Message -notlike $Expected) { throw }; $rejected = $true }
    if (-not $rejected) { throw "Expected rejection: $Scenario" }
}
& "$PSScriptRoot/status.ps1" | Out-Null
Assert-Rejected missing 'Missing container*'
Assert-Rejected foreign 'Container ownership mismatch*'
Assert-Rejected api-failure 'Stack status validation failed*'
$mock.Scenario = 'normal'
& "$PSScriptRoot/down.ps1" -WhatIf | Out-Null
if ($mock.Calls.Count -ne 0) { throw 'WhatIf mutated containers.' }
& "$PSScriptRoot/down.ps1" | Out-Null
if ($mock.Calls.Count -ne 13 -or $mock.Calls[0][-1] -ne 'agent-frontend-1') { throw 'Stop order/count incorrect.' }
$mock.Calls = @()
& "$PSScriptRoot/up.ps1" | Out-Null
if ($mock.Calls.Count -ne 13 -or $mock.Calls[0][-1] -ne 'agent-postgres-1') { throw 'Start order/count incorrect.' }
foreach ($call in $mock.Calls) {
    if ($call[-1] -match 'migrate|seed') { throw 'One-shot job was started.' }
}
Assert-Rejected docker-failure 'Failed to down*' down
Write-Output '8 self-checks passed (mock Docker/HTTP; no real container operations).'
