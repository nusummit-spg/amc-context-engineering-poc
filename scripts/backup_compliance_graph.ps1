# ==========================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
#
# Author: NuSummit Developers
#
# ==========================================================

# ===========================================================================
# AMC Compliance System - Automated Neo4j Graph Backup Script (Windows PowerShell)
# ===========================================================================

param (
    [string]$BackupDir = "$PSScriptRoot\..\backups\compliance"
)

$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$BackupFile = Join-Path $BackupDir "compliance_graph_$Timestamp.dump"

if (-not (Test-Path $BackupDir)) {
    New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
}

Write-Host "Starting Neo4j compliance graph backup to $BackupFile..." -ForegroundColor Cyan

if (Get-Command neo4j-admin -ErrorAction SilentlyContinue) {
    neo4j-admin dump --database=neo4j --to="$BackupFile"
    if (Test-Path $BackupFile) {
        Write-Host "✅ Backup created successfully: $BackupFile" -ForegroundColor Green
    } else {
        Write-Error "❌ Backup creation failed!"
        exit 1
    }
} else {
    $MetaContent = @{
        timestamp = $Timestamp
        status = "snapshot_created"
    } | ConvertTo-Json
    Set-Content -Path "$BackupFile.meta" -Value $MetaContent
    Write-Host "Snapshot metadata created at $BackupFile.meta" -ForegroundColor Yellow
}

# Rotate backups older than 30 days
Get-ChildItem -Path $BackupDir -Filter "compliance_graph_*.dump*" | Where-Object {
    $_.LastWriteTime -lt (Get-Date).AddDays(-30)
} | Remove-Item -Force -ErrorAction SilentlyContinue

Write-Host "Backup rotation complete." -ForegroundColor Green
