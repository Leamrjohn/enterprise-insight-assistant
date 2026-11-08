[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [securestring]$DatabasePassword,
    [string]$ComposeFile = "docker-compose.yml"
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$passwordHandle = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($DatabasePassword)
$plainPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($passwordHandle)
try {
    Push-Location $projectRoot
    $query = "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity, p.policyname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace LEFT JOIN pg_policies p ON p.schemaname=n.nspname AND p.tablename=c.relname WHERE n.nspname='public' AND c.relname IN ('documents','document_chunks') ORDER BY c.relname, p.policyname;"
    docker compose -f $ComposeFile exec -T -e "PGPASSWORD=$plainPassword" postgres psql -U agent_backup -d agent_platform -v ON_ERROR_STOP=1 -c $query
    if ($LASTEXITCODE -ne 0) { throw "Tenant RLS verification failed." }
}
finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordHandle)
    Pop-Location
}
