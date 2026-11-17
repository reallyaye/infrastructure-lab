[CmdletBinding()]
param(
    [string]$BackupDirectory = (Join-Path $PSScriptRoot "..\backups"),
    [ValidatePattern("^[a-z_][a-z0-9_]*$")]
    [string]$TestDatabase = "infra_lab_restore_check"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$backup = Get-ChildItem -LiteralPath $BackupDirectory -Filter "infra-lab-*.dump" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

if (-not $backup) {
    throw "No backup file was found. Run backup-postgres.ps1 first."
}

Push-Location $projectRoot
try {
    $existsCommand = 'psql -U "$POSTGRES_USER" -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = ''{0}''"' -f $TestDatabase
    [string]$exists = & docker compose exec -T database sh -c $existsCommand
    if ($exists -and $exists.Trim() -eq "1") {
        throw "Test database '$TestDatabase' already exists. Drop it manually only after confirming it is not needed."
    }

    $createCommand = 'createdb -U "$POSTGRES_USER" "{0}"' -f $TestDatabase
    & docker compose exec -T database sh -c $createCommand
    if ($LASTEXITCODE -ne 0) { throw "Could not create the isolated restore-check database." }

    $containerId = (& docker compose ps -q database).Trim()
    if (-not $containerId) { throw "Database container is not running." }

    & docker cp $backup.FullName "${containerId}:/tmp/restore_check.dump"
    if ($LASTEXITCODE -ne 0) { throw "Could not copy the backup into the database container." }

    $restoreCommand = 'pg_restore -U "$POSTGRES_USER" -d "{0}" --exit-on-error /tmp/restore_check.dump' -f $TestDatabase
    & docker compose exec -T database sh -c $restoreCommand
    $restoreExitCode = $LASTEXITCODE
    & docker compose exec -T database rm -f /tmp/restore_check.dump
    if ($restoreExitCode -ne 0) { throw "pg_restore exited with code $restoreExitCode" }

    $validateCommand = 'psql -U "$POSTGRES_USER" -d "{0}" -tAc "SELECT 1"' -f $TestDatabase
    & docker compose exec -T database sh -c $validateCommand | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "The restored database did not accept a validation query." }

    Write-Output "Restore check passed using $($backup.Name) in isolated database '$TestDatabase'."
}
finally {
    Pop-Location
}
