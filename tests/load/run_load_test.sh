#!/bin/bash
# Load test runner script for Task P0-29
# 
# Usage:
#   ./run_load_test.sh [quick|full|ci]
#
# Modes:
#   quick - 100 users, 30 seconds (development)
#   full  - 1000 users, 5 minutes (production validation)
#   ci    - 500 users, 2 minutes (CI/CD pipeline)

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PYTHON_DIR="$PROJECT_ROOT/python"
API_HOST="${API_HOST:-http://localhost:8000}"

# Test mode (default: quick)
MODE="${1:-quick}"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}RLS Load Test Runner (Task P0-29)${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Check if API server is running
echo -e "${YELLOW}Checking API server at $API_HOST...${NC}"
if ! curl -s -f "$API_HOST/health" > /dev/null 2>&1; then
    echo -e "${RED}❌ API server not responding at $API_HOST${NC}"
    echo -e "${YELLOW}Please start the API server first:${NC}"
    echo "  cd $PYTHON_DIR"
    echo "  poetry run uvicorn src.server.main:app --host 0.0.0.0 --port 8000"
    exit 1
fi
echo -e "${GREEN}✅ API server is running${NC}"
echo ""

# Configure test parameters based on mode
case "$MODE" in
    quick)
        USERS=100
        SPAWN_RATE=20
        RUN_TIME="30s"
        echo -e "${YELLOW}Mode: Quick Test (100 users, 30 seconds)${NC}"
        ;;
    full)
        USERS=1000
        SPAWN_RATE=100
        RUN_TIME="5m"
        echo -e "${YELLOW}Mode: Full Test (1000 users, 5 minutes)${NC}"
        ;;
    ci)
        USERS=500
        SPAWN_RATE=50
        RUN_TIME="2m"
        echo -e "${YELLOW}Mode: CI/CD Test (500 users, 2 minutes)${NC}"
        ;;
    *)
        echo -e "${RED}Invalid mode: $MODE${NC}"
        echo "Usage: $0 [quick|full|ci]"
        exit 1
        ;;
esac

echo "  Users: $USERS"
echo "  Spawn Rate: $SPAWN_RATE/sec"
echo "  Duration: $RUN_TIME"
echo ""

# Change to python directory
cd "$PYTHON_DIR"

# Check if locust is installed
if ! poetry run locust --version > /dev/null 2>&1; then
    echo -e "${RED}❌ Locust not installed${NC}"
    echo -e "${YELLOW}Installing dependencies...${NC}"
    poetry install --with dev
fi

# Create reports directory
REPORTS_DIR="$PROJECT_ROOT/reports/load_tests"
mkdir -p "$REPORTS_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
REPORT_FILE="$REPORTS_DIR/rls_load_test_${MODE}_${TIMESTAMP}.html"

echo -e "${GREEN}Starting load test...${NC}"
echo ""

# Run locust
poetry run locust \
    -f "$SCRIPT_DIR/test_rls_under_load.py" \
    --host="$API_HOST" \
    --users "$USERS" \
    --spawn-rate "$SPAWN_RATE" \
    --run-time "$RUN_TIME" \
    --headless \
    --html="$REPORT_FILE" \
    --loglevel INFO

# Check results
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Load Test Complete${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${YELLOW}Report saved to:${NC}"
echo "  $REPORT_FILE"
echo ""

# Parse results (simple check for now)
if [ -f "$REPORT_FILE" ]; then
    echo -e "${GREEN}✅ Test completed successfully${NC}"
    echo ""
    echo -e "${YELLOW}Next steps:${NC}"
    echo "  1. Open the HTML report in your browser"
    echo "  2. Check isolation success rate (target: 99.99%)"
    echo "  3. Review any violations in the logs"
else
    echo -e "${RED}❌ Test failed - report not generated${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}========================================${NC}"

