[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateNotNullOrEmpty()]
    [string[]]$RunPath,
    [ValidateRange(0.000001, 1000)]
    [decimal]$MaxTotalSettledCostUsd = [decimal]'0.30',
    [ValidateRange(0, 1000)]
    [decimal]$PlannedMaxCostUsd = [decimal]'0'
)

$ErrorActionPreference = 'Stop'

function ConvertTo-NonNegativeDecimal {
    param(
        [object]$Value,
        [string]$Label
    )

    $parsed = [decimal]0
    if ($null -eq $Value -or -not [decimal]::TryParse(
        [string]$Value,
        [Globalization.NumberStyles]::Number,
        [Globalization.CultureInfo]::InvariantCulture,
        [ref]$parsed
    ) -or $parsed -lt 0) {
        throw "$Label must be a non-negative decimal."
    }
    return $parsed
}

$resolvedPaths = @(
    foreach ($path in $RunPath) {
        (Resolve-Path -LiteralPath $path -ErrorAction Stop).Path
    }
)
if (@($resolvedPaths | Sort-Object -Unique).Count -ne $resolvedPaths.Count) {
    throw 'RunPath values must be unique.'
}

$entries = @(
    foreach ($path in $resolvedPaths | Sort-Object) {
        try {
            $run = Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
        } catch {
            throw "Cannot read valid evaluation run JSON: $path"
        }
        if ($run.metrics.cost_status -ne 'passed' -or $null -eq $run.metrics.settled_cost) {
            throw "Evaluation run has unknown or unsettled cost: $path"
        }
        [ordered]@{
            path = $path
            run_id = $run.run_id
            settled_cost_usd = ConvertTo-NonNegativeDecimal $run.metrics.settled_cost "settled_cost for $path"
        }
    }
)

$settledCost = [decimal]0
foreach ($entry in $entries) {
    $settledCost += $entry.settled_cost_usd
}
$projectedCost = $settledCost + $PlannedMaxCostUsd
if ($projectedCost -gt $MaxTotalSettledCostUsd) {
    throw "P0 evaluation budget exceeded: projected $projectedCost USD exceeds $MaxTotalSettledCostUsd USD."
}

[ordered]@{
    schema_version = 'p0-evaluation-budget-check/v1'
    max_total_settled_cost_usd = $MaxTotalSettledCostUsd
    settled_cost_usd = $settledCost
    planned_max_cost_usd = $PlannedMaxCostUsd
    projected_cost_usd = $projectedCost
    remaining_cost_usd = $MaxTotalSettledCostUsd - $projectedCost
    run_count = $entries.Count
    runs = $entries
} | ConvertTo-Json -Depth 4
