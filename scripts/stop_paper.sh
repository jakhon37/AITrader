#!/bin/bash
# Stop all paper trading services

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}🛑 Stopping AITrader paper trading services...${NC}"
echo ""

STOPPED=0

# Stop paper trading
if [ -f .paper_trading.pid ]; then
    PID=$(cat .paper_trading.pid)
    if ps -p $PID > /dev/null 2>&1; then
        kill $PID
        echo -e "   ${GREEN}✅ Stopped paper trading (PID: $PID)${NC}"
        STOPPED=1
    fi
    rm .paper_trading.pid
fi

# Stop monitor dashboard
if [ -f .monitor_dashboard.pid ]; then
    PID=$(cat .monitor_dashboard.pid)
    if ps -p $PID > /dev/null 2>&1; then
        kill $PID
        echo -e "   ${GREEN}✅ Stopped monitor dashboard (PID: $PID)${NC}"
        STOPPED=1
    fi
    rm .monitor_dashboard.pid
fi

# Stop feature explorer
if [ -f .feature_explorer.pid ]; then
    PID=$(cat .feature_explorer.pid)
    if ps -p $PID > /dev/null 2>&1; then
        kill $PID
        echo -e "   ${GREEN}✅ Stopped feature explorer (PID: $PID)${NC}"
        STOPPED=1
    fi
    rm .feature_explorer.pid
fi

if [ $STOPPED -eq 0 ]; then
    echo -e "${YELLOW}ℹ️  No services were running${NC}"
else
    echo ""
    echo -e "${GREEN}✅ All services stopped${NC}"
fi

# Also kill any stray streamlit processes
pkill -f "streamlit run dashboards/" 2>/dev/null || true

echo ""
