#!/bin/bash
# AITrader launcher — Web UI + paper trading (single Docker stack).
#
# Paper trading (ExecutionEngine) runs inside the FastAPI backend lifespan.
# Usage:
#   ./scripts/start_webui.sh
#
set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && cd .. && pwd)"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}🚀 AITrader — Web UI + Paper Trading (Docker)${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

if ! docker info >/dev/null 2>&1; then
    echo -e "${RED}❌ Docker daemon is not running.${NC}"
    exit 1
fi

mkdir -p "$PROJECT_DIR/logs"

echo -e "${YELLOW}Starting Web UI stack via docker_dev_webui.sh...${NC}"
"$PROJECT_DIR/docker/docker_dev_webui.sh"

echo -e "${YELLOW}⏳ Waiting for backend health (up to 60s)...${NC}"
HEALTHY=false
for i in $(seq 1 60); do
    BACKEND_PORT="${BACKEND_PORT:-8000}"
    if curl -sf "http://localhost:${BACKEND_PORT}/api/health" | grep -q '"status"'; then
        HEALTHY=true
        break
    fi
    echo -n "."
    sleep 1
done
echo ""

if [ "$HEALTHY" = false ]; then
    echo -e "${RED}❌ Backend did not become healthy.${NC}"
    docker logs aitrader-webui-backend 2>&1 | tail -30
    exit 1
fi

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}✅ Web UI + paper engine running (Docker)${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
echo -e "${BLUE}🌐 Trading Terminal:${NC} http://localhost:${FRONTEND_PORT}"
echo -e "${BLUE}📖 API Docs:${NC}        http://localhost:${BACKEND_PORT}/docs"
echo -e "${BLUE}💚 Health:${NC}           http://localhost:${BACKEND_PORT}/api/health"
echo ""
echo -e "${BLUE}🛑 Stop:${NC} ./scripts/stop_webui.sh"
echo ""