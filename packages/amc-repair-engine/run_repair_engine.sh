#!/bin/bash
# ===========================================================================
# Repair Engine Startup Script
# Runs the amc-repair-engine microservice on port 8002
# ===========================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PORT=${REPAIR_ENGINE_PORT:-8002}
HOST=${REPAIR_ENGINE_HOST:-0.0.0.0}
LOG_LEVEL=${LOG_LEVEL:-info}
RELOAD=${RELOAD:-true}

# Print header
echo -e "${BLUE}================================${NC}"
echo -e "${BLUE}  AMC Repair Engine${NC}"
echo -e "${BLUE}  Microservice Startup${NC}"
echo -e "${BLUE}================================${NC}"
echo

# Check if Python is available
if ! command -v python &> /dev/null; then
    echo -e "${RED}❌ Python not found. Please install Python 3.10+${NC}"
    exit 1
fi

PYTHON_VERSION=$(python --version 2>&1 | awk '{print $2}')
echo -e "${GREEN}✅ Python ${PYTHON_VERSION} found${NC}"

# Check if virtual environment exists
if [ ! -d "../../.venv" ]; then
    echo -e "${YELLOW}⚠️  Virtual environment not found at ../../.venv${NC}"
    echo -e "${YELLOW}   Please activate your virtual environment first:${NC}"
    echo -e "${YELLOW}   source ../../.venv/bin/activate  # Linux/Mac${NC}"
    echo -e "${YELLOW}   ../../.venv\\Scripts\\activate     # Windows${NC}"
    exit 1
fi

# Check if in venv
if [ -z "$VIRTUAL_ENV" ]; then
    echo -e "${YELLOW}⚠️  Virtual environment not activated${NC}"
    echo -e "${YELLOW}   Attempting to activate...${NC}"
    source ../../.venv/bin/activate || (echo -e "${RED}❌ Could not activate venv${NC}" && exit 1)
fi

# Verify amc-repair-engine is installed
if ! python -c "import amc_repair" 2>/dev/null; then
    echo -e "${YELLOW}⚠️  amc-repair-engine not found. Installing from source...${NC}"
    pip install -e . || (echo -e "${RED}❌ Failed to install amc-repair-engine${NC}" && exit 1)
fi

echo -e "${GREEN}✅ amc-repair-engine module found${NC}"

# Check environment variables
echo
echo -e "${BLUE}Configuration:${NC}"
echo "  Port: ${PORT}"
echo "  Host: ${HOST}"
echo "  Log Level: ${LOG_LEVEL}"
echo "  Auto-reload: ${RELOAD}"

# Check Neo4j connectivity
echo
echo -e "${BLUE}Checking dependencies...${NC}"

NEO4J_URI=${NEO4J_URI:-bolt://localhost:7687}
echo -n "  Neo4j (${NEO4J_URI}): "
if python -c "from neo4j import GraphDatabase; d=GraphDatabase.driver('${NEO4J_URI}', auth=('neo4j', 'amc@1234')); d.verify_connectivity(); d.close()" 2>/dev/null; then
    echo -e "${GREEN}✅${NC}"
else
    echo -e "${YELLOW}⚠️  Not reachable (will retry at startup)${NC}"
fi

# Start server
echo
echo -e "${BLUE}Starting Repair Engine...${NC}"
echo -e "${BLUE}📡 Listening on ${HOST}:${PORT}${NC}"
echo -e "${BLUE}📚 API Docs: http://${HOST}:${PORT}/docs${NC}"
echo

RELOAD_FLAG=""
if [ "$RELOAD" = "true" ]; then
    RELOAD_FLAG="--reload"
fi

python -m uvicorn \
    src.amc_repair.server:app \
    --host "$HOST" \
    --port "$PORT" \
    --log-level "$LOG_LEVEL" \
    $RELOAD_FLAG

