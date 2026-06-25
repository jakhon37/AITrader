#!/bin/bash
# AITrader Paper Trading Launcher — starts D10 Web UI (Docker).
#
# Paper trading runs inside the FastAPI backend lifespan (ExecutionEngine).
# Usage:
#   ./scripts/start_paper.sh
#
set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}🚀 AITrader Paper Trading (via Web UI)${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "${YELLOW}Paper trading is integrated into the Web UI backend.${NC}"
echo -e "${YELLOW}Starting Docker Web UI stack...${NC}"
echo ""

"$(dirname "${BASH_SOURCE[0]}")/start_webui.sh"

echo -e "${GREEN}Paper trading engine runs inside the backend container.${NC}"
echo -e "${GREEN}Monitor at: http://localhost:5173${NC}"
echo ""