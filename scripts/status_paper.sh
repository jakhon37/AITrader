#!/bin/bash
# Check status of paper trading services

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}📊 AITrader Service Status${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check paper trading
if [ -f .paper_trading.pid ]; then
    PID=$(cat .paper_trading.pid)
    if ps -p $PID > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Paper Trading${NC}"
        echo "   PID: $PID"
        echo "   Log: logs/paper_trading.log"
        
        # Show last few log lines
        if [ -f logs/paper_trading.log ]; then
            echo "   Last activity:"
            tail -n 2 logs/paper_trading.log | sed 's/^/     /'
        fi
    else
        echo -e "${RED}❌ Paper Trading (not running)${NC}"
    fi
else
    echo -e "${RED}❌ Paper Trading (not started)${NC}"
fi

echo ""

# Check monitor dashboard
if [ -f .monitor_dashboard.pid ]; then
    PID=$(cat .monitor_dashboard.pid)
    if ps -p $PID > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Paper Monitor Dashboard${NC}"
        echo "   PID: $PID"
        echo "   URL: http://localhost:8501"
        echo "   Log: logs/monitor_dashboard.log"
    else
        echo -e "${RED}❌ Paper Monitor Dashboard (not running)${NC}"
    fi
else
    echo -e "${RED}❌ Paper Monitor Dashboard (not started)${NC}"
fi

echo ""

# Check feature explorer
if [ -f .feature_explorer.pid ]; then
    PID=$(cat .feature_explorer.pid)
    if ps -p $PID > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Feature Explorer Dashboard${NC}"
        echo "   PID: $PID"
        echo "   URL: http://localhost:8502"
        echo "   Log: logs/feature_explorer.log"
    else
        echo -e "${RED}❌ Feature Explorer Dashboard (not running)${NC}"
    fi
else
    echo -e "${RED}❌ Feature Explorer Dashboard (not started)${NC}"
fi

echo ""
echo -e "${BLUE}========================================${NC}"

# Show portfolio stats from audit log
if [ -f logs/audit.jsonl ]; then
    NUM_EVENTS=$(wc -l < logs/audit.jsonl)
    echo -e "${BLUE}📈 Trading Activity${NC}"
    echo "   Total events: $NUM_EVENTS"
    
    # Count positions
    NUM_POSITIONS=$(grep -c "position_open" logs/audit.jsonl 2>/dev/null || echo "0")
    echo "   Positions opened: $NUM_POSITIONS"
    
    echo ""
fi

echo -e "${YELLOW}💡 Commands:${NC}"
echo "   Start: ./scripts/start_paper.sh"
echo "   Stop:  ./scripts/stop_paper.sh"
echo "   Logs:  tail -f logs/paper_trading.log"
echo ""
