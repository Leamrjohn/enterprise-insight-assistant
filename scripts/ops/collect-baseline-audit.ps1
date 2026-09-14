[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateSet('baseline', 'candidate')]
    [string]$Comparison,
    [Parameter(Mandatory)]
    [string]$PredictionFile,
    [string]$RunId = "$(Get-Date -Format 'yyyyMMddTHHmmss')",
    [switch]$RunChecks,
    [switch]$RunStaticChecks,
    [switch]$RunTests,
    [switch]$PrepareBaselineWorktree,
    [string]$BaselineRevision,
    [string]$PythonPath,
    [string]$TestEnvironmentFile
)

$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Prediction = Resolve-Path $PredictionFile

if ($PrepareBaselineWorktree) {
    if ($Comparison -ne 'baseline') { throw '-PrepareBaselineWorktree only applies to baseline.' }
    if (-not $BaselineRevision) { throw '-BaselineRevision is required with -PrepareBaselineWorktree.' }
    $Worktree = Join-Path $Root "tmp\evaluation-baseline-$RunId"
    if (Test-Path -LiteralPath $Worktree) { throw "Worktree already exists: $Worktree" }
    git -C $Root worktree add --detach $Worktree $BaselineRevision
    if ($LASTEXITCODE -ne 0) { throw "Failed to create baseline worktree for $BaselineRevision" }
    $RunRoot = $Worktree
} else {
    $RunRoot = $Root
}

$Python = if ($PythonPath) {
    (Resolve-Path $PythonPath).Path
} else {
    @(
        (Join-Path $RunRoot '.venv\Scripts\python.exe'),
        (Join-Path $RunRoot '.venv-py313\Scripts\python.exe')
    ) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}
if (-not $Python) { throw 'No project Python found. Pass -PythonPath explicitly.' }

$pythonVersion = @(& $Python --version 2>&1)
if ($LASTEXITCODE -ne 0) { throw "Project Python is not executable: $Python" }
$pipVersion = @(& $Python -m pip --version 2>&1)
if ($LASTEXITCODE -ne 0) { throw "Project pip is not healthy: $Python" }

$testEnvironmentKeys = @()
$testEnvironmentHash = $null
if ($TestEnvironmentFile) {
    $resolvedTestEnvironment = (Resolve-Path $TestEnvironmentFile).Path
    $testEnvironmentHash = (Get-FileHash -LiteralPath $resolvedTestEnvironment -Algorithm SHA256).Hash.ToLowerInvariant()
    foreach ($line in Get-Content -LiteralPath $resolvedTestEnvironment) {
        if ($line -match '^([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
            [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2], 'Process')
            $testEnvironmentKeys += $Matches[1]
        }
    }
}
$env:APP_ENV = 'test'
$env:DATABASE_NAME = 'agent_platform_test'
$env:MIGRATION_DATABASE_USER = 'agent_migrator'
$env:LOG_LEVEL = 'WARNING'
$env:LOG_DIR = './.test-logs'
$env:STORAGE_DIR = './.test-storage'

$Output = Join-Path $Root "evaluation-runs\$Comparison-$RunId"
New-Item -ItemType Directory -Path $Output | Out-Null
Copy-Item -LiteralPath $Prediction -Destination (Join-Path $Output 'prediction.md')

$dependencyHashes = @(
    Get-ChildItem -LiteralPath (Join-Path $RunRoot 'backend') -File |
        Where-Object { $_.Name -eq 'pyproject.toml' -or $_.Name -like 'requirements*.txt' } |
        Sort-Object Name |
        ForEach-Object {
            [ordered]@{
                path = "backend/$($_.Name)"
                sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
            }
        }
)
$trackedDiff = @(git -c core.autocrlf=false -C $RunRoot diff --binary)
$trackedDiffText = $trackedDiff -join "`n"
$trackedDiffHash = if ($trackedDiffText) {
    [Convert]::ToHexString(
        [Security.Cryptography.SHA256]::HashData(
            [Text.Encoding]::UTF8.GetBytes($trackedDiffText)
        )
    ).ToLowerInvariant()
} else {
    $null
}
$untrackedFiles = @(git -C $RunRoot ls-files --others --exclude-standard)
$untrackedManifest = @(
    foreach ($path in $untrackedFiles) {
        [ordered]@{
            path = $path
            git_blob_hash = (git -C $RunRoot hash-object -- $path).Trim()
        }
    }
)

$dockerComposeOutput = @(docker compose version 2>&1 | ForEach-Object { "$_" })
$dockerComposeExit = $LASTEXITCODE
$dockerComposeConfigOutput = @(
    docker compose -f (Join-Path $RunRoot 'docker-compose.yml') config --quiet 2>&1 |
        ForEach-Object { "$_" }
)
$dockerComposeConfigExit = $LASTEXITCODE
$dockerImagesOutput = @(
    docker compose -f (Join-Path $RunRoot 'docker-compose.yml') images 2>&1 |
        ForEach-Object { "$_" }
)
$dockerImagesExit = $LASTEXITCODE

# `pip freeze` tries to resolve this project's editable Git location and fails when
# the Windows path contains non-ASCII characters. The package inventory is what the
# comparison needs, so avoid editable-path resolution and record the command/exit.
$pipInventoryOutput = @(
    & $Python -m pip list --format=freeze --exclude-editable 2>&1 |
        ForEach-Object { "$_" }
)
$pipInventoryExit = $LASTEXITCODE

Push-Location (Join-Path $RunRoot 'backend')
try {
    $alembicHeadsOutput = @(
        & $Python -m alembic -c alembic.ini heads 2>&1 |
            ForEach-Object { "$_" }
    )
    $alembicHeadsExit = $LASTEXITCODE
} finally {
    Pop-Location
}

$Environment = [ordered]@{
    comparison = $Comparison
    run_root = $RunRoot
    git_revision = (git -C $RunRoot rev-parse HEAD).Trim()
    git_status = @(git -C $RunRoot status --short)
    python_path = $Python
    python = $pythonVersion
    pip = $pipVersion
    pip_inventory = [ordered]@{
        command = 'python -m pip list --format=freeze --exclude-editable'
        exit_code = $pipInventoryExit
        output = $pipInventoryOutput
    }
    pytest = @(& $Python -m pytest --version 2>&1)
    ruff = @(& $Python -m ruff --version 2>&1)
    docker_compose = [ordered]@{
        exit_code = $dockerComposeExit
        output = $dockerComposeOutput
    }
    docker_compose_config = [ordered]@{
        exit_code = $dockerComposeConfigExit
        output = $dockerComposeConfigOutput
    }
    docker_images = [ordered]@{
        exit_code = $dockerImagesExit
        output = $dockerImagesOutput
    }
    alembic_heads = [ordered]@{
        exit_code = $alembicHeadsExit
        output = $alembicHeadsOutput
    }
    test_environment_template_sha256 = $testEnvironmentHash
    test_environment_keys = @($testEnvironmentKeys | Sort-Object -Unique)
    collected_at_utc = (Get-Date).ToUniversalTime().ToString('o')
}
$Environment | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 (Join-Path $Output 'environment.json')
git -C $RunRoot status --short | Set-Content -Encoding utf8 (Join-Path $Output 'git-status.txt')
git -c core.autocrlf=false -C $RunRoot diff --name-status | Set-Content -Encoding utf8 (Join-Path $Output 'tracked-diff.txt')
git -c core.autocrlf=false -C $RunRoot diff --numstat | Set-Content -Encoding utf8 (Join-Path $Output 'tracked-numstat.txt')
$untrackedFiles | Set-Content -Encoding utf8 (Join-Path $Output 'untracked-files.txt')
@{
    tracked_diff_sha256 = $trackedDiffHash
    dependencies = $dependencyHashes
    untracked_files = $untrackedManifest
} | ConvertTo-Json -Depth 6 | Set-Content -Encoding utf8 (Join-Path $Output 'source-manifest.json')

Push-Location (Join-Path $RunRoot 'backend')
try {
    $collectOutput = @(& $Python -m pytest --collect-only -q 2>&1)
    $collectExit = $LASTEXITCODE
    $collectOutput | Set-Content -Encoding utf8 (Join-Path $Output 'pytest-collect.txt')
} finally {
    Pop-Location
}

$checkResults = [ordered]@{
    pytest_collect_exit_code = $collectExit
    ruff_exit_code = $null
    pytest_exit_code = $null
}

if ($RunChecks) {
    $RunStaticChecks = $true
    $RunTests = $true
}

if ($RunStaticChecks -or $RunTests) {
    Push-Location (Join-Path $RunRoot 'backend')
    try {
        if ($RunStaticChecks) {
            & $Python -m ruff check app tests *>&1 | Set-Content -Encoding utf8 (Join-Path $Output 'ruff.txt')
            $checkResults.ruff_exit_code = $LASTEXITCODE
        }
        if ($RunTests) {
            & $Python -m pytest tests -q -m 'not e2e and not slow' *>&1 | Set-Content -Encoding utf8 (Join-Path $Output 'pytest.txt')
            $checkResults.pytest_exit_code = $LASTEXITCODE
        }
    } finally {
        Pop-Location
    }
}
$checkResults | ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $Output 'checks.json')

Write-Output $Output
