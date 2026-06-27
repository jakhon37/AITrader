#!/usr/bin/env bash
# Stop native (non-Docker) AITrader processes.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PID_DIR="$PROJECT_DIR/logs"

stop_pid_file() {
  local name="$1"
  local file="$PID_DIR/${name}.pid"
  if [[ -f "$file" ]]; then
    local pid
    pid=$(cat "$file")
    kill "$pid" 2>/dev/null || true
    rm -f "$file"
    echo "Stopped $name (pid $pid)"
  fi
}

stop_pid_file backend
stop_pid_file frontend

for port in 8000 5173; do
  if command -v fuser >/dev/null 2>&1; then
    fuser -k "${port}/tcp" 2>/dev/null || true
  fi
done

if systemctl is-active --quiet aitrader-backend 2>/dev/null; then
  echo "aitrader-backend systemd service is still running."
  echo "  sudo systemctl stop aitrader-backend"
fi

echo "Done."