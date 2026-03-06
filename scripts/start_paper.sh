#!/bin/bash
# AITrader Paper Trading Launcher
# Starts paper trading + dashboards for real-time simulation

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Configuration
PAPER_TRADING_PORT=5000
MONITOR_DASHBOARD_PORT=8501
FEATURE_EXPLORER_PORT=8502

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}🚀 AITrader Paper Trading Launcher${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check if already running
if [ -f .paper_trading.pid ]; then
    PID=$(cat .paper_trading.pid)
    if ps -p $PID > /dev/null 2>&1; then
        echo -e "${YELLOW}⚠️  Paper trading already running (PID: $PID)${NC}"
        echo -e "${YELLOW}   Run './scripts/stop_paper.sh' first${NC}"
        exit 1
    fi
fi

# Parse arguments
CAPITAL=${CAPITAL:-100000}
SYMBOLS=${SYMBOLS:-"eurusd"}
INTERVAL=${INTERVAL:-3600}

while [[ $# -gt 0 ]]; do
    case $1 in
        --capital)
            CAPITAL="$2"
            shift 2
            ;;
        --symbols)
            SYMBOLS="$2"
            shift 2
            ;;
        --interval)
            INTERVAL="$2"
            shift 2
            ;;
        --no-live)
            NO_LIVE="--no-live"
            shift
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

echo -e "${GREEN}📊 Configuration:${NC}"
echo "   Capital: \$$CAPITAL"
echo "   Symbols: $SYMBOLS"
echo "   Interval: ${INTERVAL}s"
echo "   Data Source: ${NO_LIVE:+Historical CSV}${NO_LIVE:-Live Yahoo Finance}"
echo ""

# Create logs directory
mkdir -p logs

# Start paper trading in background
echo -e "${YELLOW}1. Starting paper trading...${NC}"
nohup python scripts/run_paper.py \
    --capital $CAPITAL \
    --symbols $SYMBOLS \
    --interval $INTERVAL \
    --timeframe $TIMEFRAME \
    $NO_LIVE \
    > logs/paper_trading.log 2>&1 &

PAPER_PID=$!
echo $PAPER_PID > .paper_trading.pid
echo -e "   ${GREEN}✅ Paper trading started (PID: $PAPER_PID)${NC}"
echo "   📄 Logs: logs/paper_trading.log"
echo ""

# Wait a bit for paper trading to initialize
sleep 2

# Start paper monitor dashboard
echo -e "${YELLOW}2. Starting paper monitor dashboard...${NC}"
nohup streamlit run dashboards/paper_monitor.py \
    --server.port $MONITOR_DASHBOARD_PORT \
    --server.headless true \
    > logs/monitor_dashboard.log 2>&1 &

MONITOR_PID=$!
echo $MONITOR_PID > .monitor_dashboard.pid
echo -e "   ${GREEN}✅ Monitor dashboard started (PID: $MONITOR_PID)${NC}"
echo "   🌐 URL: http://localhost:$MONITOR_DASHBOARD_PORT"
echo "   📄 Logs: logs/monitor_dashboard.log"
echo ""

# Start feature explorer dashboard
echo -e "${YELLOW}3. Starting feature explorer dashboard...${NC}"
nohup streamlit run dashboards/feature_explorer.py \
    --server.port $FEATURE_EXPLORER_PORT \
    --server.headless true \
    > logs/feature_explorer.log 2>&1 &

EXPLORER_PID=$!
echo $EXPLORER_PID > .feature_explorer.pid
echo -e "   ${GREEN}✅ Feature explorer started (PID: $EXPLORER_PID)${NC}"
echo "   🌐 URL: http://localhost:$FEATURE_EXPLORER_PORT"
echo "   📄 Logs: logs/feature_explorer.log"
echo ""

# Wait for services to start
echo -e "${YELLOW}⏳ Waiting for services to initialize...${NC}"
sleep 5

# Check if processes are still running
FAILED=0

if ! ps -p $PAPER_PID > /dev/null 2>&1; then
    echo -e "${RED}❌ Paper trading failed to start${NC}"
    echo "   Check logs/paper_trading.log for errors"
    FAILED=1
fi

if ! ps -p $MONITOR_PID > /dev/null 2>&1; then
    echo -e "${RED}❌ Monitor dashboard failed to start${NC}"
    echo "   Check logs/monitor_dashboard.log for errors"
    FAILED=1
fi

if ! ps -p $EXPLORER_PID > /dev/null 2>&1; then
    echo -e "${RED}❌ Feature explorer failed to start${NC}"
    echo "   Check logs/feature_explorer.log for errors"
    FAILED=1
fi

if [ $FAILED -eq 1 ]; then
    echo ""
    echo -e "${RED}⚠️  Some services failed to start. Cleaning up...${NC}"
    ./scripts/stop_paper.sh
    exit 1
fi

# Success
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}✅ All services running successfully!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${BLUE}📊 Dashboards:${NC}"
echo "   • Paper Monitor: http://localhost:$MONITOR_DASHBOARD_PORT"
echo "   • Feature Explorer: http://localhost:$FEATURE_EXPLORER_PORT"
echo ""
echo -e "${BLUE}📝 Logs:${NC}"
echo "   • Paper Trading: tail -f logs/paper_trading.log"
echo "   • Monitor: tail -f logs/monitor_dashboard.log"
echo "   • Feature Explorer: tail -f logs/feature_explorer.log"
echo "   • Audit Trail: tail -f logs/audit.jsonl"
echo ""
echo -e "${BLUE}🛑 To stop all services:${NC}"
echo "   ./scripts/stop_paper.sh"
echo ""
echo -e "${YELLOW}💡 Tip: Open the dashboards in your browser to monitor real-time trading!${NC}"
echo ""
