#!/usr/bin/env bash
# Status for native / Oracle Cloud deployment.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND_PORT="${BACKEND_PORT:-8000}"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "=== AITrader native status ==="
echo "Project: $PROJECT_DIR"
echo ""

if systemctl is-active --quiet aitrader-backend 2>/dev/null; then
  echo -e "systemd backend: ${GREEN}active${NC}"
  systemctl status aitrader-backend --no-pager -l 2>/dev/null | head -5 || true
else
  echo -e "systemd backend: ${YELLOW}not running via systemd${NC}"
fi

if curl -sf "http://127.0.0.1:${BACKEND_PORT}/api/health" >/tmp/aitrader_health.json 2>/dev/null; then
  echo -e "API health:        ${GREEN}OK${NC}"
  python3 -c "import json; d=json.load(open('/tmp/aitrader_health.json')); print(' ', d.get('status', d))" 2>/dev/null || true
else
  echo -e "API health:        ${RED}unreachable${NC} (port ${BACKEND_PORT})"
fi

if systemctl is-active --quiet nginx 2>/dev/null; then
  echo -e "nginx:             ${GREEN}active${NC} (UI on port 80)"
else
  echo -e "nginx:             ${YELLOW}inactive${NC}"
fi

echo ""
echo "Memory:"
free -h | sed 's/^/  /'
echo ""
echo "Disk:"
df -h / | sed 's/^/  /'

if [[ -f "$PROJECT_DIR/logs/backend.log" ]]; then
  echo ""
  echo "Last backend log lines:"
  tail -5 "$PROJECT_DIR/logs/backend.log" | sed 's/^/  /'
fi

rm -f /tmp/aitrader_health.json