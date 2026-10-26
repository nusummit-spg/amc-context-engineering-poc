# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

[CmdletBinding()]
param(
    [string]$ApiBase = "http://localhost:8000",
    [string]$OutputRoot = "",
    [switch]$SkipQueries
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    $repoRoot = Split-Path -Parent $PSScriptRoot | Split-Path -Parent
    $OutputRoot = Join-Path $repoRoot "logs/baseline"
}
else {
    $repoRoot = Split-Path -Parent $PSScriptRoot | Split-Path -Parent
}

$timestamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
$runDir = Join-Path $OutputRoot $timestamp
New-Item -ItemType Directory -Path $runDir -Force | Out-Null

$ApiBase = $ApiBase.TrimEnd('/')
$fixturePath = Join-Path (Split-Path -Parent $PSScriptRoot | Split-Path -Parent) "Docs/baseline/query_fixtures.json"
$manifest = [ordered]@{
    schema_version = "1.0"
    started_at_utc = [DateTime]::UtcNow.ToString("o")
    api_base = $ApiBase
    host = $env:COMPUTERNAME
    powershell_version = $PSVersionTable.PSVersion.ToString()
    probes = @()
    notes = @(
        "Read-only collector: no ingestion, cache-clear, graph seeding, or index rebuild operation was requested.",
        "A failed endpoint is evidence and is preserved in the manifest."
    )
}

function Save-Json {
    param([Parameter(Mandatory = $true)]$Value, [Parameter(Mandatory = $true)][string]$Path)
    $Value | ConvertTo-Json -Depth 30 | Set-Content -Path $Path -Encoding utf8
}

function Invoke-ApiProbe {
    param(
        [Parameter(Mandatory = $true)][string]$Id,
        [Parameter(Mandatory = $true)][string]$Method,
        [Parameter(Mandatory = $true)][string]$Path,
        $Body = $null
    )

    $uri = "$ApiBase$Path"
    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    $record = [ordered]@{ id = $Id; method = $Method; uri = $uri; success = $false }
    try {
        $params = @{ Uri = $uri; Method = $Method; TimeoutSec = 240; ErrorAction = "Stop" }
        if ($null -ne $Body) {
            $params.ContentType = "application/json"
            $params.Body = ($Body | ConvertTo-Json -Depth 20 -Compress)
        }
        $result = Invoke-RestMethod @params
        $record.success = $true
        $record.result_file = "$Id.json"
        Save-Json -Value $result -Path (Join-Path $runDir $record.result_file)
    }
    catch {
        $record.error = $_.Exception.Message
        if ($_.Exception.Response) {
            $record.http_status = [int]$_.Exception.Response.StatusCode
        }
        if ($_.ErrorDetails.Message) { $record.error_body = $_.ErrorDetails.Message }
    }
    finally {
        $stopwatch.Stop()
        $record.elapsed_ms = [math]::Round($stopwatch.Elapsed.TotalMilliseconds, 1)
        $script:manifest.probes += [pscustomobject]$record
    }
}

Invoke-ApiProbe -Id "status" -Method "GET" -Path "/api/status"
Invoke-ApiProbe -Id "documents" -Method "GET" -Path "/api/docs"
Invoke-ApiProbe -Id "taxonomy" -Method "GET" -Path "/api/taxonomy"
Invoke-ApiProbe -Id "graph" -Method "GET" -Path "/api/graph?limit=100"

if (-not $SkipQueries) {
    $fixtures = Get-Content -Raw $fixturePath | ConvertFrom-Json
    foreach ($fixture in $fixtures.queries) {
        Invoke-ApiProbe -Id ("query_" + $fixture.id) -Method "POST" -Path "/api/query" -Body @{
            query = $fixture.query
            mode = $fixture.mode
        }
    }

    $history = @()
    $turn = 1
    foreach ($question in $fixtures.chat_scenario.turns) {
        Invoke-ApiProbe -Id ("chat_" + $fixtures.chat_scenario.id + "_turn" + $turn) -Method "POST" -Path "/api/chat" -Body @{
            query = $question
            session_id = ("baseline-" + $timestamp)
            history = $history
            mode = $fixtures.chat_scenario.mode
        }
        $responsePath = Join-Path $runDir ("chat_" + $fixtures.chat_scenario.id + "_turn" + $turn + ".json")
        if (Test-Path $responsePath) {
            $response = Get-Content -Raw $responsePath | ConvertFrom-Json
            $answer = $response.hybrid.answer.answer
            $history += @{ role = "user"; content = $question }
            $history += @{ role = "assistant"; content = $answer }
        }
        $turn++
    }
}

$manifest.completed_at_utc = [DateTime]::UtcNow.ToString("o")
$manifest.successful_probes = @($manifest.probes | Where-Object { $_.success }).Count
$manifest.failed_probes = @($manifest.probes | Where-Object { -not $_.success }).Count
Save-Json -Value $manifest -Path (Join-Path $runDir "manifest.json")

$summary = @(
    "Baseline directory: $runDir",
    "Successful probes: $($manifest.successful_probes)",
    "Failed probes: $($manifest.failed_probes)",
    "Raw responses and errors are listed in manifest.json."
)
$summary | Set-Content -Path (Join-Path $runDir "SUMMARY.txt") -Encoding utf8
$summary | ForEach-Object { Write-Host $_ }
