# E2: regenerate the backend lock files in a Linux CPython 3.12 container, the
# platform every image and CI job installs on (Windows resolves differently).
#
#   scripts/ops/update-locks.ps1                         # re-lock, versions unchanged
#   scripts/ops/update-locks.ps1 -UpgradePackage pillow,pypdf
#
# Upgrading or adding a dependency needs approval (AGENTS.md); review the lock
# diff and run the tests before committing.
[CmdletBinding()]
param(
    [string[]]$UpgradePackage = @()
)
$ErrorActionPreference = 'Stop'

$image = 'python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1'
$backend = (Resolve-Path (Join-Path $PSScriptRoot '..\..\backend')).Path

docker run --rm --name agent-update-locks -v "${backend}:/backend" -w /backend $image `
    bash scripts/deps/update_locks.sh @UpgradePackage
if ($LASTEXITCODE -ne 0) { throw "update_locks.sh failed with exit code $LASTEXITCODE" }
