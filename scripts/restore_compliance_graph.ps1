# ==========================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
#
# Author: NuSummit Developers
#
# ==========================================================

# ===========================================================================
# AMC Compliance System - Neo4j Graph Restore Script (Windows PowerShell)
# ===========================================================================

param (
    [Parameter(Mandatory=$true)]
    [string]$BackupFile
)

if (-not (Test-Path $BackupFile)) {
    Write-Error "❌ Error: Backup file not found: $BackupFile"
    exit 1
}

Write-Host "Restoring Neo4j database from $BackupFile..." -ForegroundColor Cyan

if (Get-Command neo4j-admin -ErrorAction SilentlyContinue) {
    Stop-Service neo4j -ErrorAction SilentlyContinue
    neo4j-admin load --database=neo4j --from="$BackupFile" --force
    Start-Service neo4j -ErrorAction SilentlyContinue
    Write-Host "✅ Restore completed successfully." -ForegroundColor Green
} else {
    Write-Host "neo4j-admin CLI not found; please verify Neo4j service installation." -ForegroundColor Yellow
}
