#!/bin/bash
# Stop AITrader Web UI Docker containers.
set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && cd .. && pwd)"

echo -e "${YELLOW}🛑 Stopping AITrader Web UI...${NC}"

docker stop aitrader-webui-backend aitrader-webui-frontend 2>/dev/null || true

if command -v docker-compose &>/dev/null; then
    COMPOSE_CMD="docker-compose"
elif docker compose version &>/dev/null; then
    COMPOSE_CMD="docker compose"
else
    COMPOSE_CMD=""
fi

if [ -n "$COMPOSE_CMD" ]; then
    cd "$PROJECT_DIR/docker"
    $COMPOSE_CMD -f docker-compose.webui.yml down 2>/dev/null || true
    cd "$PROJECT_DIR"
    $COMPOSE_CMD -f docker-compose.yml down 2>/dev/null || true
fi

if [ -f "$PROJECT_DIR/.frontend.pid" ]; then
    PID=$(cat "$PROJECT_DIR/.frontend.pid")
    kill "$PID" 2>/dev/null || true
    rm -f "$PROJECT_DIR/.frontend.pid"
fi

# Free ports if a stray local Vite is still listening
for port in 8000 5173; do
    if command -v lsof >/dev/null 2>&1; then
        pids=$(lsof -ti "tcp:${port}" -sTCP:LISTEN 2>/dev/null || true)
        if [ -n "$pids" ]; then
            echo -e "   Stopping local process on port ${port}..."
            kill $pids 2>/dev/null || true
        fi
    fi
done

echo -e "${GREEN}✅ Web UI stopped${NC}"