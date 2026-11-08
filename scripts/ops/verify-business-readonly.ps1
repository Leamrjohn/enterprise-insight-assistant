[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [securestring]$DatabasePassword,
    [Parameter(Mandatory)]
    [ValidatePattern("^[A-Za-z_][A-Za-z0-9_]*$")]
    [string]$ReadonlyRole,
    [Parameter(Mandatory)]
    [ValidatePattern("^[A-Za-z_][A-Za-z0-9_]*$")]
    [string]$Database,
    [ValidatePattern("^[A-Za-z_][A-Za-z0-9_]*$")]
    [string]$DatabaseService = "business_db",
    [ValidatePattern("^[A-Za-z_][A-Za-z0-9_]*$")]
    [string]$DatabaseAdminUser = "business_owner",
    [string]$ComposeFile = "docker-compose.yml"
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$passwordHandle = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($DatabasePassword)
$plainPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($passwordHandle)
try {
    Push-Location $projectRoot
    # Catalog checks avoid issuing a write attempt against customer data.
    $writeQuery = "SELECT c.relname, has_table_privilege('$ReadonlyRole', c.oid, 'INSERT,UPDATE,DELETE,TRUNCATE') AS can_write FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'public' AND c.relkind IN ('r','p') ORDER BY c.relname;"
    $output = docker compose -f $ComposeFile exec -T -e "PGPASSWORD=$plainPassword" $DatabaseService psql -U $DatabaseAdminUser -d $Database -v ON_ERROR_STOP=1 -At -F '|' -c $writeQuery
    if ($LASTEXITCODE -ne 0) { throw "Readonly role catalog check failed." }
    if ($output | Select-String -Pattern '\|t$') { throw "Readonly role has write privileges." }
    $roleQuery = "SELECT rolsuper, rolcreaterole, rolcreatedb, rolbypassrls FROM pg_roles WHERE rolname = '$ReadonlyRole';"
    $roleFlags = docker compose -f $ComposeFile exec -T -e "PGPASSWORD=$plainPassword" $DatabaseService psql -U $DatabaseAdminUser -d $Database -v ON_ERROR_STOP=1 -At -c $roleQuery
    if ($LASTEXITCODE -ne 0 -or $roleFlags.Trim() -ne 'f|f|f|f') { throw "Readonly role has elevated privileges or does not exist." }
    Write-Host "Readonly verification passed for $ReadonlyRole on $Database."
}
finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordHandle)
    Pop-Location
}
