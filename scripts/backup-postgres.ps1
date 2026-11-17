[CmdletBinding()]
param(
    [string]$BackupDirectory = (Join-Path $PSScriptRoot "..\backups")
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot

New-Item -ItemType Directory -Force -Path $BackupDirectory | Out-Null
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupPath = Join-Path $BackupDirectory "infra-lab-$timestamp.dump"

Push-Location $projectRoot
try {
    $containerId = (& docker compose ps -q database).Trim()
    if (-not $containerId) {
        throw "Database container is not running. Start the stack before creating a backup."
    }

    # Credentials stay inside the container environment and are not written to the backup command.
    & docker compose exec -T database sh -c 'pg_dump -Fc -U "$POSTGRES_USER" -f /tmp/infra_lab_backup.dump "$POSTGRES_DB"'
    if ($LASTEXITCODE -ne 0) {
        throw "pg_dump exited with code $LASTEXITCODE"
    }

    & docker cp "${containerId}:/tmp/infra_lab_backup.dump" $backupPath
    $copyExitCode = $LASTEXITCODE
    & docker compose exec -T database rm -f /tmp/infra_lab_backup.dump
    if ($copyExitCode -ne 0) {
        Remove-Item -LiteralPath $backupPath -Force -ErrorAction SilentlyContinue
        throw "Could not copy the backup from the database container."
    }

    if ((Get-Item -LiteralPath $backupPath).Length -eq 0) {
        Remove-Item -LiteralPath $backupPath -Force
        throw "Backup file is empty."
    }

    Get-ChildItem -LiteralPath $BackupDirectory -Filter "infra-lab-*.dump" |
        Sort-Object LastWriteTime -Descending |
        Select-Object -Skip 14 |
        Remove-Item -Force

    Write-Output "Backup created: $backupPath"
}
finally {
    Pop-Location
}
