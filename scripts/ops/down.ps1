[CmdletBinding(SupportsShouldProcess)]
param()
& (Join-Path $PSScriptRoot 'stack.ps1') -Mode down @PSBoundParameters
