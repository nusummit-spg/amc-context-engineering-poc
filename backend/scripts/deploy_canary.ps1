# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

param(
    [string]$TrafficPercent = "10"
)

Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host "DEPLOYING CONTEXT ENGINEERING CANARY ROLLOUT: $TrafficPercent% TRAFFIC" -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan

# Set environment variables for feature enablement
$env:ENABLE_HYDE_CACHE = "true"
$env:ENABLE_HYDE_IN_ORCHESTRATOR = "true"
$env:ENABLE_GLINER_SKIP = "true"
$env:ENABLE_CYPHER_AUTO_CORRECTION = "true"
$env:ENABLE_PARALLELIZATION = "true"
$env:ENABLE_QUERY_DECOMPOSITION = "true"

Write-Host "Configured Canary Environment Variables:"
Write-Host "  - ENABLE_HYDE_CACHE:              $env:ENABLE_HYDE_CACHE"
Write-Host "  - ENABLE_HYDE_IN_ORCHESTRATOR:    $env:ENABLE_HYDE_IN_ORCHESTRATOR"
Write-Host "  - ENABLE_GLINER_SKIP:             $env:ENABLE_GLINER_SKIP"
Write-Host "  - ENABLE_CYPHER_AUTO_CORRECTION:  $env:ENABLE_CYPHER_AUTO_CORRECTION"
Write-Host "  - ENABLE_PARALLELIZATION:         $env:ENABLE_PARALLELIZATION"
Write-Host "  - ENABLE_QUERY_DECOMPOSITION:     $env:ENABLE_QUERY_DECOMPOSITION"
Write-Host "  - CANARY_TRAFFIC_WEIGHT:          $TrafficPercent%"

Write-Host "`nCanary profile activated successfully." -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Soak monitor (exits non-zero on regression):"
Write-Host "       python scripts/monitor_canary.py --hours 24 --interval 60"
Write-Host "  2. Promotion gate (exits non-zero if unhealthy or inconclusive):"
Write-Host "       python scripts/check_canary_health.py --window-hours 24"
Write-Host "  3. Live dashboard:"
Write-Host "       python scripts/dashboard_realtime.py --watch"
Write-Host ""
Write-Host "  To roll back, re-run with every ENABLE_* flag set to false."
