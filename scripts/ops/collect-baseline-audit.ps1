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
    [switch]$FreezeP0CandidateSnapshot,
    [string]$P0CandidatePathManifest,
    [switch]$RequireRuntimeSourceMatch,
    [switch]$PrepareBaselineWorktree,
    [string]$BaselineRevision,
    [string]$PythonPath,
    [string]$TestEnvironmentFile,
    [int]$TestDatabasePort
)

$ErrorActionPreference = 'Stop'
# The workspace path contains non-ASCII characters; pip prints that path.
$env:PYTHONUTF8 = '1'

function Test-P0ExecutableCandidatePath {
    param([string]$Path)

    $normalizedPath = $Path.Replace('\\', '/')
    if ($normalizedPath -like 'backend/.evaluation-runs/*') { return $false }
    # Documents are recorded separately in the append-only evidence ledger;
    # snapshotting them would mix non-executable user edits into the candidate.
    if ($normalizedPath -like 'docs/*') { return $false }
    if ($normalizedPath -like 'backend/*') { return $true }
    if ($normalizedPath -in @(
        'scripts/ops/collect-baseline-audit.ps1',
        'scripts/ops/assert-p0-evaluation-budget.ps1',
        'scripts/ops/inspect-queue.ps1',
        'scripts/ops/verify-stack.ps1',
        'scripts/ops/p0-candidate-paths.json'
    )) { return $true }
    return $normalizedPath -in @(
        'AGENTS.md',
        '.gitignore',
        'README.md',
        'CONTRIBUTING.md',
        'PRODUCT.md',
        'SECURITY.md',
        'docker-compose.yml'
    )
}

function Get-P0CandidatePaths {
    param(
        [string]$ManifestPath,
        [string[]]$ChangedPaths
    )

    if (-not $ManifestPath) {
        throw '-P0CandidatePathManifest is required with -FreezeP0CandidateSnapshot.'
    }
    try {
        $manifestBytes = [IO.File]::ReadAllBytes((Resolve-Path $ManifestPath))
        $manifest = [Text.Encoding]::UTF8.GetString($manifestBytes) | ConvertFrom-Json
    } catch {
        throw "Cannot read valid P0 candidate path manifest: $ManifestPath"
    }
    if ($manifest.schema_version -ne 'p0-candidate-paths-v1') {
        throw 'P0 candidate path manifest schema_version must be p0-candidate-paths-v1.'
    }
    $paths = @($manifest.paths)
    if ($paths.Count -eq 0) {
        throw 'P0 candidate path manifest paths must be non-empty.'
    }
    $selected = @(
        foreach ($path in $paths) {
            if ($path -isnot [string] -or -not $path -or $path -match '(^|[\\/])\.\.([\\/]|$)') {
                throw 'P0 candidate path manifest contains an invalid relative path.'
            }
            $normalizedPath = $path.Replace('\\', '/')
            if (-not (Test-P0ExecutableCandidatePath $normalizedPath)) {
                throw "P0 candidate path is outside the approved executable scope: $normalizedPath"
            }
            if ($normalizedPath -notin $ChangedPaths) {
                throw "P0 candidate path is not a current tracked or untracked change: $normalizedPath"
            }
            $normalizedPath
        }
    )
    if (@($selected | Sort-Object -Unique).Count -ne $selected.Count) {
        throw 'P0 candidate path manifest paths must be unique.'
    }
    return [ordered]@{
        paths = @($selected | Sort-Object)
        sha256 = [Convert]::ToHexString(
            [Security.Cryptography.SHA256]::HashData($manifestBytes)
        ).ToLowerInvariant()
    }
}

function Get-CanonicalTrackedChangeManifest {
    param([string]$RepositoryRoot)

    $paths = @(git -C $RepositoryRoot diff HEAD --name-only 2>$null | Sort-Object -Unique)
    return @(
        foreach ($path in $paths) {
            $statusLine = @(git -C $RepositoryRoot diff HEAD --name-status -- $path 2>$null | Select-Object -First 1)[0]
            $fullPath = Join-Path $RepositoryRoot $path
            [ordered]@{
                path = $path
                status = $statusLine.Split("`t")[0]
                blob_hash = if (Test-Path -LiteralPath $fullPath) {
                    (git -C $RepositoryRoot hash-object --path=$path -- $path).Trim()
                } else {
                    $null
                }
            }
        }
    )
}

function Get-ManifestSha256 {
    param([object[]]$Manifest)

    $manifestJson = @($Manifest) | ConvertTo-Json -Depth 5 -Compress
    return [Convert]::ToHexString(
        [Security.Cryptography.SHA256]::HashData(
            [Text.Encoding]::UTF8.GetBytes($manifestJson)
        )
    ).ToLowerInvariant()
}

function Get-ContainerRuntimeSourceFingerprint {
    param(
        [string]$RepositoryRoot,
        [object[]]$WorkspaceManifest
    )

    $payload = @($WorkspaceManifest) | ConvertTo-Json -Depth 4 -Compress
    $comparisonProgram = @'
import hashlib
import json
import pathlib
import sys

entries = json.load(sys.stdin)
root = pathlib.Path("/app")
result = []
for entry in entries:
    path = root / entry["path"]
    actual = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    result.append(
        {
            "path": entry["path"],
            "workspace_sha256": entry["sha256"],
            "container_sha256": actual,
            "matches": actual == entry["sha256"],
        }
    )
print(json.dumps(result, sort_keys=True))
'@
    $services = @()
    foreach ($service in @('api', 'worker')) {
        $output = @(
            $payload |
                docker compose -f (Join-Path $RepositoryRoot 'docker-compose.yml') exec -T $service python -c $comparisonProgram 2>&1 |
                ForEach-Object { "$_" }
        )
        $exitCode = $LASTEXITCODE
        $records = @()
        if ($exitCode -eq 0) {
            try {
                $records = @(($output -join "`n") | ConvertFrom-Json)
            } catch {
                $exitCode = 1
                $output += "Unable to parse container fingerprint output: $($_.Exception.Message)"
            }
        }
        $actualManifest = @(
            foreach ($record in $records) {
                [ordered]@{
                    path = $record.path
                    sha256 = $record.container_sha256
                }
            }
        )
        $services += [ordered]@{
            service = $service
            exit_code = $exitCode
            matched_paths = @($records | Where-Object { $_.matches }).Count
            mismatched_paths = @($records | Where-Object { -not $_.matches }).Count
            missing_paths = @($records | Where-Object { $null -eq $_.container_sha256 }).Count
            mismatch_paths = @($records | Where-Object { -not $_.matches } | ForEach-Object { $_.path })
            container_manifest_sha256 = if ($exitCode -eq 0) { Get-ManifestSha256 $actualManifest } else { $null }
            output = if ($exitCode -eq 0) { @() } else { $output }
        }
    }
    $passed = @($WorkspaceManifest).Count -gt 0 -and $services.Count -eq 2 -and @($services | Where-Object {
        $_.exit_code -ne 0 -or $_.mismatched_paths -ne 0
    }).Count -eq 0
    return [ordered]@{
        scope = 'candidate runtime source: backend/app plus runtime dependency/config files'
        workspace_manifest_sha256 = Get-ManifestSha256 $WorkspaceManifest
        path_count = @($WorkspaceManifest).Count
        status = if ($passed) { 'passed' } else { 'failed' }
        services = $services
    }
}

if ($FreezeP0CandidateSnapshot -and $Comparison -ne 'candidate') {
    throw '-FreezeP0CandidateSnapshot only applies to candidate.'
}
if ($FreezeP0CandidateSnapshot -and -not $P0CandidatePathManifest) {
    throw '-P0CandidatePathManifest is required with -FreezeP0CandidateSnapshot.'
}
if ($RequireRuntimeSourceMatch -and -not $FreezeP0CandidateSnapshot) {
    throw '-RequireRuntimeSourceMatch requires -FreezeP0CandidateSnapshot.'
}
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
$testEnvironmentOverrides = [ordered]@{}
$p0TestEnvironmentKeys = @(
    'DATABASE_HOST',
    'DATABASE_PORT',
    'DATABASE_NAME',
    'DATABASE_USER',
    'DATABASE_PASSWORD',
    'BUSINESS_DATABASE_HOST',
    'BUSINESS_DATABASE_PORT',
    'BUSINESS_DATABASE_NAME',
    'BUSINESS_DATABASE_USER',
    'BUSINESS_DATABASE_PASSWORD'
)
if ($TestEnvironmentFile) {
    $resolvedTestEnvironment = (Resolve-Path $TestEnvironmentFile).Path
    $testEnvironmentHash = (Get-FileHash -LiteralPath $resolvedTestEnvironment -Algorithm SHA256).Hash.ToLowerInvariant()
    foreach ($line in Get-Content -LiteralPath $resolvedTestEnvironment) {
        if ($line -match '^([A-Za-z_][A-Za-z0-9_]*)=(.*)$' -and $p0TestEnvironmentKeys -contains $Matches[1]) {
            # Do not leak model or object-storage credentials from a developer .env into P0 tests.
            [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2], 'Process')
            $testEnvironmentKeys += $Matches[1]
        }
    }
}
if ($TestDatabasePort) {
    $env:DATABASE_PORT = "$TestDatabasePort"
    $testEnvironmentOverrides.DATABASE_PORT = $env:DATABASE_PORT
}
$env:APP_ENV = 'test'
$env:DATABASE_NAME = 'agent_platform_test'
$env:MIGRATION_DATABASE_USER = 'agent_migrator'
$env:LOG_LEVEL = 'WARNING'
$env:LOG_DIR = './.test-logs'
$env:STORAGE_DIR = './.test-storage'

$Output = Join-Path $Root "artifacts\p0\$RunId"
New-Item -ItemType Directory -Force -Path $Output | Out-Null
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
$trackedChangeManifest = Get-CanonicalTrackedChangeManifest $RunRoot
$trackedChangeManifestJson = $trackedChangeManifest | ConvertTo-Json -Depth 3 -Compress
$trackedDiffHash = if ($trackedChangeManifest.Count) {
    [Convert]::ToHexString(
        [Security.Cryptography.SHA256]::HashData(
            [Text.Encoding]::UTF8.GetBytes($trackedChangeManifestJson)
        )
    ).ToLowerInvariant()
} else {
    $null
}
$untrackedFiles = @(git -c core.quotePath=false -C $RunRoot ls-files --others --exclude-standard)
$untrackedManifest = @(
    foreach ($path in $untrackedFiles) {
        $normalizedPath = $path.Replace('\\', '/')
        $isP0ExecutablePath = Test-P0ExecutableCandidatePath $normalizedPath
        [ordered]@{
            path = $normalizedPath
            content_hash_status = if ($isP0ExecutablePath) { 'hashed' } else { 'excluded_non_p0' }
            git_blob_hash = if ($isP0ExecutablePath) {
                (git -C $RunRoot hash-object -- $path).Trim()
            } else {
                $null
            }
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
$dockerComposeServices = @(
    docker compose -f (Join-Path $RunRoot 'docker-compose.yml') config --services 2>$null
)
$dockerImagesOutput = @(
    docker compose -f (Join-Path $RunRoot 'docker-compose.yml') images $dockerComposeServices 2>&1 |
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

$containerRuntimeSourceFingerprint = $null
$Environment = [ordered]@{
    comparison = $Comparison
    run_root = $RunRoot
    git_revision = (git -C $RunRoot rev-parse HEAD).Trim()
    git_status = @(git -C $RunRoot status --short)
    python_path = $Python
    python = $pythonVersion
    python_utf8 = $env:PYTHONUTF8
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
    test_environment_overrides = $testEnvironmentOverrides
    container_runtime_source_fingerprint = $containerRuntimeSourceFingerprint
    collected_at_utc = (Get-Date).ToUniversalTime().ToString('o')
}
git -C $RunRoot status --short | Set-Content -Encoding utf8 (Join-Path $Output 'git-status.txt')
git -C $RunRoot diff HEAD --name-status 2>$null | Set-Content -Encoding utf8 (Join-Path $Output 'tracked-diff.txt')
git -C $RunRoot diff HEAD --numstat 2>$null | Set-Content -Encoding utf8 (Join-Path $Output 'tracked-numstat.txt')
$untrackedFiles | Set-Content -Encoding utf8 (Join-Path $Output 'untracked-files.txt')
@{
    tracked_diff_sha256 = $trackedDiffHash
    tracked_changes = $trackedChangeManifest
    dependencies = $dependencyHashes
    untracked_files = $untrackedManifest
} | ConvertTo-Json -Depth 6 | Set-Content -Encoding utf8 (Join-Path $Output 'source-manifest.json')

if ($FreezeP0CandidateSnapshot) {
    $Snapshot = Join-Path $Output 'candidate-snapshot'
    New-Item -ItemType Directory -Path $Snapshot | Out-Null
    $allChangedPaths = @(
        @(
            git -C $RunRoot diff HEAD --name-only 2>$null
            $untrackedFiles
        ) | ForEach-Object { $_.Replace('\\', '/') } | Sort-Object -Unique
    )
    $p0Candidate = Get-P0CandidatePaths -ManifestPath $P0CandidatePathManifest -ChangedPaths $allChangedPaths
    Copy-Item -LiteralPath (Resolve-Path $P0CandidatePathManifest) -Destination (Join-Path $Snapshot 'p0-candidate-paths.json')
    $trackedCandidatePaths = @(
        git -C $RunRoot diff HEAD --name-only 2>$null |
            ForEach-Object { $_.Replace('\\', '/') } |
            Where-Object { $_ -in $p0Candidate.paths } |
            Sort-Object -Unique
    )
    $untrackedCandidatePaths = @(
        $untrackedFiles |
            ForEach-Object { $_.Replace('\\', '/') } |
            Where-Object { $_ -in $p0Candidate.paths } |
            Sort-Object -Unique
    )
    $runtimeCandidatePaths = @(
        @($trackedCandidatePaths + $untrackedCandidatePaths) |
            Where-Object {
                $_ -like 'backend/app/*' -or $_ -in @(
                    'backend/alembic.ini',
                    'backend/pyproject.toml',
                    'backend/requirements.txt',
                    'backend/requirements-ml.txt'
                )
            } |
            Sort-Object -Unique
    )
    $runtimeSourceManifest = @(
        foreach ($path in $runtimeCandidatePaths) {
            [ordered]@{
                path = $path.Substring('backend/'.Length)
                sha256 = (Get-FileHash -LiteralPath (Join-Path $RunRoot $path) -Algorithm SHA256).Hash.ToLowerInvariant()
            }
        }
    )
    $containerRuntimeSourceFingerprint = Get-ContainerRuntimeSourceFingerprint -RepositoryRoot $RunRoot -WorkspaceManifest $runtimeSourceManifest
    $Environment.container_runtime_source_fingerprint = $containerRuntimeSourceFingerprint
    $excludedCandidatePaths = @(
        @(
            git -C $RunRoot diff HEAD --name-only 2>$null
            $untrackedFiles
        ) |
            Where-Object { -not (Test-P0ExecutableCandidatePath $_) } |
            Sort-Object -Unique
    )
    $trackedCandidatePaths | Set-Content -Encoding utf8 (Join-Path $Snapshot 'tracked-paths.txt')
    $untrackedCandidatePaths | Set-Content -Encoding utf8 (Join-Path $Snapshot 'untracked-paths.txt')
    $excludedCandidatePaths | Set-Content -Encoding utf8 (Join-Path $Snapshot 'excluded-paths.txt')

    $PatchPath = Join-Path $Snapshot 'candidate.patch'
    if ($trackedCandidatePaths.Count) {
        @(& git -C $RunRoot diff HEAD --binary -- $trackedCandidatePaths 2>$null) |
            Set-Content -Encoding utf8 $PatchPath
        if ($LASTEXITCODE -ne 0) { throw 'Failed to create candidate patch.' }
    } else {
        Set-Content -Encoding utf8 $PatchPath ''
    }

    $UntrackedArchive = Join-Path $Snapshot 'untracked-files.zip'
    if ($untrackedCandidatePaths.Count) {
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $archive = [System.IO.Compression.ZipFile]::Open(
            $UntrackedArchive,
            [System.IO.Compression.ZipArchiveMode]::Create
        )
        try {
            foreach ($path in $untrackedCandidatePaths) {
                [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
                    $archive,
                    (Join-Path $RunRoot $path),
                    $path.Replace('\\', '/'),
                    [System.IO.Compression.CompressionLevel]::Optimal
                ) | Out-Null
            }
        } finally {
            $archive.Dispose()
        }
    }

    $snapshotManifest = [ordered]@{
        base_revision = (git -C $RunRoot rev-parse HEAD).Trim()
        scope = 'P0 executable candidate: backend excluding backend/.evaluation-runs, named P0 preflight scripts, and selected root configuration; docs excluded'
        p0_candidate_path_manifest_sha256 = $p0Candidate.sha256
        p0_candidate_paths = $p0Candidate.paths
        tracked_paths = $trackedCandidatePaths
        untracked_paths = $untrackedCandidatePaths
        runtime_source_paths = $runtimeCandidatePaths
        runtime_source_workspace_manifest_sha256 = $containerRuntimeSourceFingerprint.workspace_manifest_sha256
        excluded_paths = $excludedCandidatePaths
        patch_sha256 = (Get-FileHash -LiteralPath $PatchPath -Algorithm SHA256).Hash.ToLowerInvariant()
        untracked_archive_sha256 = if (Test-Path -LiteralPath $UntrackedArchive) {
            (Get-FileHash -LiteralPath $UntrackedArchive -Algorithm SHA256).Hash.ToLowerInvariant()
        } else {
            $null
        }
    }
    $snapshotManifest | ConvertTo-Json -Depth 5 |
        Set-Content -Encoding utf8 (Join-Path $Snapshot 'snapshot-manifest.json')
}

$Environment | ConvertTo-Json -Depth 8 | Set-Content -Encoding utf8 (Join-Path $Output 'environment.json')

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
            & $Python -m pytest tests -q -rs -m 'not e2e and not slow' *>&1 | Set-Content -Encoding utf8 (Join-Path $Output 'pytest.txt')
            $checkResults.pytest_exit_code = $LASTEXITCODE
        }
    } finally {
        Pop-Location
    }
}
$checkResults | ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $Output 'checks.json')

Write-Output $Output
if ($RequireRuntimeSourceMatch -and $containerRuntimeSourceFingerprint.status -ne 'passed') {
    throw 'Runtime source fingerprint does not match both running API and Worker containers.'
}
