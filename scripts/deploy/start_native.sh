#!/usr/bin/env bash
# Start AITrader without Docker (dev / manual mode — no nginx required).
#
# Runs:
#   - uvicorn backend on 0.0.0.0:8000
#   - vite dev frontend on 0.0.0.0:5173
#
# Usage:
#   ./scripts/deploy/start_native.sh
#   ./scripts/deploy/start_native.sh --background
#
set -euo pipefail

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKGROUND=false
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --background|-b) BACKGROUND=true; shift ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

PID_DIR="$PROJECT_DIR/logs"
mkdir -p "$PID_DIR"

if [[ ! -d "$PROJECT_DIR/.venv" ]]; then
  echo -e "${RED}Missing .venv — run scripts/deploy/install_oracle_cloud.sh first${NC}"
  exit 1
fi

# shellcheck disable=SC1091
source "$PROJECT_DIR/.venv/bin/activate"

export PYTHONPATH="$PROJECT_DIR/src"
export CONFIG_DIR="$PROJECT_DIR/config"
export ENV="${ENV:-dev}"

if [[ -f "$PROJECT_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$PROJECT_DIR/.env"
  set +a
fi

free_port() {
  local port="$1"
  if command -v fuser >/dev/null 2>&1; then
    fuser -k "${port}/tcp" 2>/dev/null || true
  elif command -v lsof >/dev/null 2>&1; then
    local pids
    pids=$(lsof -ti "tcp:${port}" -sTCP:LISTEN 2>/dev/null || true)
    [[ -n "$pids" ]] && kill $pids 2>/dev/null || true
  fi
}

echo -e "${BLUE}Starting AITrader (native)...${NC}"
free_port "$BACKEND_PORT"
free_port "$FRONTEND_PORT"

if [[ "$BACKGROUND" == true ]]; then
  cd "$PROJECT_DIR"
  nohup uvicorn src.api.main:app \
    --host 0.0.0.0 \
    --port "$BACKEND_PORT" \
    --workers 1 \
    >> "$PID_DIR/backend.log" 2>&1 &
  echo $! > "$PID_DIR/backend.pid"

  cd "$PROJECT_DIR/frontend"
  export VITE_API_BASE=/api
  export VITE_PROXY_TARGET="http://127.0.0.1:${BACKEND_PORT}"
  export VITE_WS_URL="ws://127.0.0.1:${BACKEND_PORT}/ws"
  nohup npm run dev -- --host 0.0.0.0 --port "$FRONTEND_PORT" \
    >> "$PID_DIR/frontend.log" 2>&1 &
  echo $! > "$PID_DIR/frontend.pid"
  cd "$PROJECT_DIR"

  echo -e "${YELLOW}Waiting for backend health...${NC}"
  for _ in $(seq 1 45); do
    if curl -sf "http://127.0.0.1:${BACKEND_PORT}/api/health" | grep -q '"status"'; then
      break
    fi
    sleep 1
  done

  PUBLIC_IP="$(curl -sf --max-time 3 ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')"
  echo -e "${GREEN}✅ Running in background${NC}"
  echo "  UI:      http://${PUBLIC_IP}:${FRONTEND_PORT}"
  echo "  API:     http://${PUBLIC_IP}:${BACKEND_PORT}/api/health"
  echo "  Logs:    tail -f $PID_DIR/backend.log"
  echo "  Stop:    $PROJECT_DIR/scripts/deploy/stop_native.sh"
else
  trap 'kill 0' EXIT
  cd "$PROJECT_DIR"
  uvicorn src.api.main:app \
    --host 0.0.0.0 \
    --port "$BACKEND_PORT" \
    --workers 1 &
  sleep 2
  cd "$PROJECT_DIR/frontend"
  export VITE_API_BASE=/api
  export VITE_PROXY_TARGET="http://127.0.0.1:${BACKEND_PORT}"
  export VITE_WS_URL="ws://127.0.0.1:${BACKEND_PORT}/ws"
  npm run dev -- --host 0.0.0.0 --port "$FRONTEND_PORT" &
  wait
fi