#!/usr/bin/env bash
# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

TRAFFIC_PERCENT=${1:-10}

echo "================================================================="
echo "DEPLOYING CONTEXT ENGINEERING CANARY ROLLOUT: ${TRAFFIC_PERCENT}% TRAFFIC"
echo "================================================================="

export ENABLE_HYDE_CACHE="true"
export ENABLE_HYDE_IN_ORCHESTRATOR="true"
export ENABLE_GLINER_SKIP="true"
export ENABLE_CYPHER_AUTO_CORRECTION="true"
export ENABLE_PARALLELIZATION="true"
export ENABLE_QUERY_DECOMPOSITION="true"
export CANARY_TRAFFIC_WEIGHT="${TRAFFIC_PERCENT}%"

echo "Configured Canary Environment Variables:"
echo "  - ENABLE_HYDE_CACHE:              ${ENABLE_HYDE_CACHE}"
echo "  - ENABLE_HYDE_IN_ORCHESTRATOR:    ${ENABLE_HYDE_IN_ORCHESTRATOR}"
echo "  - ENABLE_GLINER_SKIP:             ${ENABLE_GLINER_SKIP}"
echo "  - ENABLE_CYPHER_AUTO_CORRECTION:  ${ENABLE_CYPHER_AUTO_CORRECTION}"
echo "  - ENABLE_PARALLELIZATION:         ${ENABLE_PARALLELIZATION}"
echo "  - ENABLE_QUERY_DECOMPOSITION:     ${ENABLE_QUERY_DECOMPOSITION}"
echo "  - CANARY_TRAFFIC_WEIGHT:          ${CANARY_TRAFFIC_WEIGHT}"

echo ""
echo "Canary profile activated successfully."
echo ""
echo "Next steps:"
echo "  1. Soak monitor (blocks for the soak duration, exits non-zero on regression):"
echo "       python scripts/monitor_canary.py --hours 24 --interval 60"
echo "  2. Promotion gate (exits non-zero if the canary is unhealthy or inconclusive):"
echo "       python scripts/check_canary_health.py --window-hours 24"
echo "  3. Live dashboard:"
echo "       python scripts/dashboard_realtime.py --watch"
echo ""
echo "  To roll back, re-run with every ENABLE_* flag set to false."
