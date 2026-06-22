#!/bin/bash
# Stop all AITrader Web UI services
#

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get the absolute path to the project directory
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && cd .. && pwd)"

echo -e "${YELLOW}🛑 Stopping AITrader Web UI services...${NC}"
echo ""

STOPPED=0

# Stop Docker backend container
if docker ps -a --format '{{.Names}}' | grep -q "^aitrader-webui-backend$"; then
    echo -e "${YELLOW}   Stopping backend container...${NC}"
    docker stop aitrader-webui-backend >/dev/null 2>&1 || true
    echo -e "   ${GREEN}✅ Stopped backend container (aitrader-webui-backend)${NC}"
    STOPPED=1
fi

# Stop frontend Vite server
if [ -f "$PROJECT_DIR/.frontend.pid" ]; then
    PID=$(cat "$PROJECT_DIR/.frontend.pid")
    if ps -p $PID > /dev/null 2>&1; then
        kill $PID 2>/dev/null || true
        echo -e "   ${GREEN}✅ Stopped frontend Vite server (PID: $PID)${NC}"
        STOPPED=1
    fi
    rm "$PROJECT_DIR/.frontend.pid"
fi

# Also kill any stray Vite servers
pkill -f "vite" 2>/dev/null || true

if [ $STOPPED -eq 0 ]; then
    echo -e "${YELLOW}ℹ️  No Web UI services were running${NC}"
else
    echo ""
    echo -e "${GREEN}✅ All Web UI services stopped successfully${NC}"
fi

echo ""
