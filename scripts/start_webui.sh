#!/bin/bash
# AITrader Web UI Launcher
# Starts FastAPI backend (in Docker) and React/Vite frontend (locally)
#
# Usage:
#   ./scripts/start_webui.sh
#

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Configuration
BACKEND_PORT=8000
FRONTEND_PORT=5173

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}🚀 AITrader Web UI Launcher${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Get the absolute path to the project directory
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && cd .. && pwd)"

# Verify docker is running
if ! docker info >/dev/null 2>&1; then
    echo -e "${RED}❌ Docker daemon is not running. Please start Docker first.${NC}"
    exit 1
fi

# Verify Node.js / npm available for frontend
if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
    echo -e "${RED}❌ Node.js and npm are required to run the frontend.${NC}"
    echo -e "   Install from https://nodejs.org/ (v18+ recommended) and try again."
    exit 1
fi

# Create logs directory
mkdir -p "$PROJECT_DIR/logs"

# Stop existing Web UI services
echo -e "${YELLOW}🧹 Stopping any existing Web UI services...${NC}"
docker stop aitrader-webui-backend 2>/dev/null || true

if [ -f "$PROJECT_DIR/.frontend.pid" ]; then
    PID=$(cat "$PROJECT_DIR/.frontend.pid")
    if ps -p $PID > /dev/null 2>&1; then
        kill $PID 2>/dev/null || true
    fi
    rm "$PROJECT_DIR/.frontend.pid"
fi
# Also kill any stray Vite/npm instances in the frontend folder just in case
pkill -f "vite" 2>/dev/null || true

sleep 1
echo ""

# 1. Start FastAPI Backend in Docker (in the background)
echo -e "${YELLOW}1. Starting FastAPI backend in Docker on port $BACKEND_PORT...${NC}"
ENV_FILE_ARG=""
if [ -f "$PROJECT_DIR/.env" ]; then
    ENV_FILE_ARG="--env-file $PROJECT_DIR/.env"
fi

docker run -d --rm \
    --name aitrader-webui-backend \
    -p ${BACKEND_PORT}:${BACKEND_PORT} \
    $ENV_FILE_ARG \
    -v "$PROJECT_DIR/src:/app/src:ro" \
    -v "$PROJECT_DIR/config:/app/config:ro" \
    -v "$PROJECT_DIR/data:/app/data:rw" \
    -v "$PROJECT_DIR/models:/app/models:ro" \
    -v "$PROJECT_DIR/logs:/app/logs:rw" \
    -e PYTHONPATH=/app/src:/app \
    -e CONFIG_DIR=/app/config \
    -e PYTHONUNBUFFERED=1 \
    -w /app \
    aitrader-dev:latest \
    uvicorn src.api.main:app --host 0.0.0.0 --port ${BACKEND_PORT}

echo -e "   ${GREEN}✅ Backend container launched${NC}"
echo "   📄 Docker Container: aitrader-webui-backend"
echo "   📄 System Logs: tail -f logs/app.log"
echo ""

# 2. Start React Frontend locally (Vite dev server)
echo -e "${YELLOW}2. Starting React frontend (Vite dev server) locally...${NC}"
if [ ! -f "$PROJECT_DIR/frontend/node_modules/.bin/vite" ]; then
    echo -e "${YELLOW}   Installing / restoring npm dependencies (missing vite binary)...${NC}"
    cd "$PROJECT_DIR/frontend" && npm install
    if [ ! -f "$PROJECT_DIR/frontend/node_modules/.bin/vite" ]; then
        echo -e "${RED}   ❌ npm install did not produce vite. Check your Node.js / npm setup.${NC}"
        exit 1
    fi
fi

cd "$PROJECT_DIR/frontend"
nohup npm run dev > ../logs/frontend.log 2>&1 &
FRONTEND_PID=$!
echo $FRONTEND_PID > ../.frontend.pid

# Give Vite a moment to start or fail fast (e.g. missing binary)
sleep 1.5
if ! ps -p $FRONTEND_PID > /dev/null 2>&1; then
    echo -e "${RED}   ❌ Frontend process died immediately after launch.${NC}"
    echo -e "   Last log lines:"
    tail -10 ../logs/frontend.log 2>/dev/null || true
    exit 1
fi

echo -e "   ${GREEN}✅ Frontend process started (PID: $FRONTEND_PID)${NC}"
echo "   📄 Frontend Logs: tail -f logs/frontend.log"
echo ""

# Wait for backend to initialize and become healthy (handling pip install time)
echo -e "${YELLOW}⏳ Waiting for backend to initialize and install dependencies (up to 30s)...${NC}"
HEALTHY=false
for i in {1..30}; do
    # First, make sure the container is still running
    if ! docker ps -f name=aitrader-webui-backend --format '{{.Names}}' | grep -q "aitrader-webui-backend"; then
        echo -e "${RED}❌ Backend container exited unexpectedly.${NC}"
        break
    fi
    
    # Try fetching the health check endpoint
    if curl -s --max-time 1 "http://localhost:${BACKEND_PORT}/api/health" | grep -q '"status"'; then
        HEALTHY=true
        break
    fi
    
    # Show progress
    echo -n "."
    sleep 1
done
echo ""

if [ "$HEALTHY" = false ]; then
    echo -e "${RED}❌ Backend failed to initialize or become healthy on port ${BACKEND_PORT}!${NC}"
    echo -e "${YELLOW}Container status / logs: ${NC}"
    docker logs aitrader-webui-backend || echo "No logs or container already removed"
    exit 1
fi

# Final frontend process health check (in case it died during backend wait)
if ! ps -p $FRONTEND_PID > /dev/null 2>&1; then
    echo -e "${RED}❌ Frontend failed to start! Check logs/frontend.log for errors${NC}"
    echo -e "   Last 15 lines of frontend log:"
    tail -15 "$PROJECT_DIR/logs/frontend.log" 2>/dev/null || true
    exit 1
fi

# Success message
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}✅ Web UI Running Successfully!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${BLUE}🌐 Access Terminal Web UI:${NC}"
echo "   👉 http://localhost:$FRONTEND_PORT"
echo ""
echo -e "${BLUE}🔌 API Services:${NC}"
echo "   • Swagger Docs: http://localhost:$BACKEND_PORT/docs"
echo "   • Health Check: http://localhost:$BACKEND_PORT/api/health"
echo ""
echo -e "${BLUE}🛑 To stop all services:${NC}"
echo "   ./scripts/stop_webui.sh"
echo ""
