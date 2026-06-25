#!/bin/bash
# Start D10 Web UI in Docker — env image only, project files bind-mounted (no COPY).
set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && cd .. && pwd)"
NETWORK="aitrader-net"
BACKEND_IMAGE="aitrader-dev:latest"
FRONTEND_IMAGE="node:20-alpine"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

free_port() {
    local port="$1"
    local label="$2"

    # Stop any Docker container publishing this host port
    while IFS= read -r cid; do
        [ -z "$cid" ] && continue
        echo "   Stopping container $cid ($label port $port)..."
        docker stop "$cid" 2>/dev/null || true
    done < <(docker ps -q --filter "publish=${port}" 2>/dev/null || true)

    # Kill stray local dev servers (e.g. old `npm run dev` on the Mac)
    if command -v lsof >/dev/null 2>&1; then
        local pids
        pids=$(lsof -ti "tcp:${port}" -sTCP:LISTEN 2>/dev/null || true)
        if [ -n "$pids" ]; then
            echo "   Freeing local process on port $port (PID: $pids)..."
            kill $pids 2>/dev/null || true
            sleep 1
        fi
    fi
}

if ! docker info >/dev/null 2>&1; then
    echo "❌ Docker daemon is not running."
    exit 1
fi

if ! docker image inspect "$BACKEND_IMAGE" >/dev/null 2>&1; then
    echo "🔨 Building $BACKEND_IMAGE (Python env only)..."
    "$PROJECT_DIR/docker/docker_dev_build.sh"
fi

ENV_FILE_ARG=""
if [ -f "$PROJECT_DIR/.env" ]; then
    ENV_FILE_ARG="--env-file $PROJECT_DIR/.env"
fi

echo "🧹 Stopping existing Web UI containers..."
docker stop aitrader-webui-backend aitrader-webui-frontend 2>/dev/null || true
docker rm aitrader-webui-frontend 2>/dev/null || true

if [ -f "$PROJECT_DIR/.frontend.pid" ]; then
    OLD_PID=$(cat "$PROJECT_DIR/.frontend.pid")
    kill "$OLD_PID" 2>/dev/null || true
    rm -f "$PROJECT_DIR/.frontend.pid"
fi

echo "🧹 Freeing ports ${BACKEND_PORT} and ${FRONTEND_PORT}..."
free_port "$BACKEND_PORT" "backend"
free_port "$FRONTEND_PORT" "frontend"

docker network create "$NETWORK" 2>/dev/null || true

echo "🚀 Starting backend (aitrader-dev)..."
docker run -d --rm \
    --name aitrader-webui-backend \
    --network "$NETWORK" \
    -p "${BACKEND_PORT}:8000" \
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
    "$BACKEND_IMAGE" \
    uvicorn src.api.main:app --host 0.0.0.0 --port 8000

echo "🚀 Starting frontend (node:20-alpine, mounted frontend/)..."
docker run -d --rm \
    --name aitrader-webui-frontend \
    --network "$NETWORK" \
    -p "${FRONTEND_PORT}:5173" \
    -v "$PROJECT_DIR/frontend:/app:rw" \
    -v aitrader-frontend-node-modules:/app/node_modules \
    -w /app \
    -e VITE_API_BASE=/api \
    -e VITE_PROXY_TARGET=http://aitrader-webui-backend:8000 \
    -e VITE_WS_URL="ws://localhost:${BACKEND_PORT}/ws" \
    "$FRONTEND_IMAGE" \
    sh -c "npm ci && npm run dev -- --host 0.0.0.0 --port 5173"

echo ""
echo "✅ Web UI running (bind-mounted, no image COPY):"
echo "   Terminal:  http://localhost:${FRONTEND_PORT}"
echo "   API docs:  http://localhost:${BACKEND_PORT}/docs"
echo "   Health:    http://localhost:${BACKEND_PORT}/api/health"
echo ""
echo "🛑 Stop: ./scripts/stop_webui.sh"