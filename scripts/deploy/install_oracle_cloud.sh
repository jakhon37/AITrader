#!/usr/bin/env bash
# AITrader — bare-metal install for Oracle Cloud (Ubuntu, no Docker).
#
# Target: dedicated small VM (~1–2 GB RAM). Sets up swap, Python venv, Node build,
# nginx reverse proxy, and systemd service for the FastAPI backend.
#
# Usage (on a fresh Ubuntu instance):
#   git clone <your-repo-url> ~/AITrader
#   cd ~/AITrader
#   chmod +x scripts/deploy/*.sh
#   ./scripts/deploy/install_oracle_cloud.sh
#
# Options:
#   --install-dir PATH     Project root (default: parent of scripts/)
#   --public-host HOST     Public IP/hostname for WebSocket URL at build time
#   --swap SIZE            Swap file size, e.g. 2G (default: 2G; recommended on 1GB RAM)
#   --skip-nginx           Skip nginx; use scripts/deploy/start_native.sh (dev mode)
#   --skip-systemd         Skip systemd unit install
#
set -euo pipefail

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
PUBLIC_HOST=""
SWAP_SIZE="2G"
SKIP_NGINX=false
SKIP_SYSTEMD=false
BACKEND_PORT="${BACKEND_PORT:-8000}"
SERVICE_USER="${SUDO_USER:-$USER}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --install-dir) INSTALL_DIR="$2"; shift 2 ;;
    --public-host) PUBLIC_HOST="$2"; shift 2 ;;
    --swap) SWAP_SIZE="$2"; shift 2 ;;
    --skip-nginx) SKIP_NGINX=true; shift ;;
    --skip-systemd) SKIP_SYSTEMD=true; shift ;;
    -h|--help)
      sed -n '2,20p' "$0"
      exit 0
      ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

log()  { echo -e "${BLUE}$*${NC}"; }
ok()   { echo -e "${GREEN}$*${NC}"; }
warn() { echo -e "${YELLOW}$*${NC}"; }
fail() { echo -e "${RED}$*${NC}"; exit 1; }

if [[ ! -f "$INSTALL_DIR/pyproject.toml" ]]; then
  fail "Not an AITrader root: $INSTALL_DIR (missing pyproject.toml)"
fi

if [[ "$(id -u)" -eq 0 ]]; then
  fail "Run as your normal user (ubuntu), not root. Script uses sudo where needed."
fi

log "=========================================="
log "AITrader Oracle Cloud install (no Docker)"
log "=========================================="
log "Install dir: $INSTALL_DIR"
log "User:        $SERVICE_USER"
echo ""

# ── 1. System packages ───────────────────────────────────────────────────────
log "Installing system packages..."
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
  python3 python3-venv python3-dev python3-pip \
  build-essential git curl ca-certificates \
  nginx rsync

if ! command -v node >/dev/null 2>&1 || [[ "$(node -v 2>/dev/null | sed 's/v//' | cut -d. -f1)" -lt 20 ]]; then
  log "Installing Node.js 20..."
  curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y nodejs
fi
ok "Node $(node -v) · Python $(python3 --version)"

# ── 2. Swap (critical on 1 GB RAM) ───────────────────────────────────────────
if [[ "$(swapon --show 2>/dev/null | wc -l)" -eq 0 ]]; then
  log "Creating ${SWAP_SIZE} swap file..."
  sudo fallocate -l "$SWAP_SIZE" /swapfile 2>/dev/null || sudo dd if=/dev/zero of=/swapfile bs=1M count=$(( ${SWAP_SIZE%G} * 1024 )) status=progress
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
  if ! grep -q '/swapfile' /etc/fstab; then
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
  fi
  ok "Swap enabled: $(free -h | awk '/Swap/{print $2}')"
else
  warn "Swap already active — skipping"
fi

# ── 3. Data directories ──────────────────────────────────────────────────────
mkdir -p "$INSTALL_DIR/data/raw" "$INSTALL_DIR/data/state" "$INSTALL_DIR/logs" "$INSTALL_DIR/config"

if [[ ! -f "$INSTALL_DIR/.env" ]]; then
  cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
  warn "Created .env from .env.example — edit API keys before going live:"
  warn "  nano $INSTALL_DIR/.env"
fi

# ── 4. Python virtualenv ───────────────────────────────────────────────────────
log "Creating Python venv and installing package..."
python3 -m venv "$INSTALL_DIR/.venv"
# shellcheck disable=SC1091
source "$INSTALL_DIR/.venv/bin/activate"
pip install -U pip wheel setuptools
pip install -e "$INSTALL_DIR[live_data,webui]"

# ── 5. Frontend production build ───────────────────────────────────────────────
if [[ -z "$PUBLIC_HOST" ]]; then
  PUBLIC_HOST="$(curl -sf --max-time 5 ifconfig.me 2>/dev/null || curl -sf --max-time 5 icanhazip.com 2>/dev/null || hostname -I | awk '{print $1}')"
fi
log "Building frontend (public host: $PUBLIC_HOST)..."
cd "$INSTALL_DIR/frontend"
export VITE_API_BASE=/api
export VITE_WS_URL="ws://${PUBLIC_HOST}/ws"
npm ci
npm run build
cd "$INSTALL_DIR"

# ── 6. Nginx (production: static UI + API/WS proxy) ─────────────────────────────
if [[ "$SKIP_NGINX" == false ]]; then
  log "Configuring nginx..."
  sudo tee /etc/nginx/sites-available/aitrader >/dev/null <<NGINX
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;

    root ${INSTALL_DIR}/frontend/dist;
    index index.html;

    client_max_body_size 10m;

    location / {
        try_files \$uri \$uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:${BACKEND_PORT}/api/;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 300s;
    }

    location /docs {
        proxy_pass http://127.0.0.1:${BACKEND_PORT}/docs;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
    }

    location /openapi.json {
        proxy_pass http://127.0.0.1:${BACKEND_PORT}/openapi.json;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
    }

    location /ws {
        proxy_pass http://127.0.0.1:${BACKEND_PORT}/ws;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_read_timeout 86400s;
    }
}
NGINX

  sudo ln -sf /etc/nginx/sites-available/aitrader /etc/nginx/sites-enabled/aitrader
  sudo rm -f /etc/nginx/sites-enabled/default
  sudo nginx -t
  sudo systemctl enable nginx
  sudo systemctl restart nginx
  ok "nginx serving UI on port 80"
fi

# ── 7. systemd backend service ─────────────────────────────────────────────────
if [[ "$SKIP_SYSTEMD" == false ]]; then
  log "Installing systemd service..."
  sudo tee /etc/systemd/system/aitrader-backend.service >/dev/null <<UNIT
[Unit]
Description=AITrader FastAPI backend (paper trading + live data)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${INSTALL_DIR}
Environment=PYTHONPATH=${INSTALL_DIR}/src
Environment=CONFIG_DIR=${INSTALL_DIR}/config
Environment=ENV=dev
Environment=WEB_UI_URL=http://${PUBLIC_HOST}
EnvironmentFile=-${INSTALL_DIR}/.env
ExecStart=${INSTALL_DIR}/.venv/bin/uvicorn src.api.main:app --host 127.0.0.1 --port ${BACKEND_PORT} --workers 1
Restart=on-failure
RestartSec=10
StandardOutput=append:${INSTALL_DIR}/logs/backend.log
StandardError=append:${INSTALL_DIR}/logs/backend.log

# 1 GB RAM instance: keep memory bounded
MemoryMax=700M
MemoryHigh=600M

[Install]
WantedBy=multi-user.target
UNIT

  sudo systemctl daemon-reload
  sudo systemctl enable aitrader-backend
  sudo systemctl restart aitrader-backend
  ok "aitrader-backend.service started"
fi

# ── 8. Firewall hint ───────────────────────────────────────────────────────────
if command -v ufw >/dev/null 2>&1 && sudo ufw status 2>/dev/null | grep -q inactive; then
  warn "UFW is inactive. In Oracle Cloud, open port 80 in the VCN Security List / NSG."
fi

echo ""
ok "=========================================="
ok "Install complete"
ok "=========================================="
echo ""
echo "  Trading UI:  http://${PUBLIC_HOST}/"
echo "  API health:  http://${PUBLIC_HOST}/api/health"
echo "  API docs:    http://${PUBLIC_HOST}/docs"
echo ""
echo "  Edit secrets:  nano ${INSTALL_DIR}/.env"
echo "  Backend logs:  tail -f ${INSTALL_DIR}/logs/backend.log"
echo "  Status:        ${INSTALL_DIR}/scripts/deploy/status_native.sh"
echo "  Restart:       sudo systemctl restart aitrader-backend"
echo ""
warn "Oracle Cloud: ensure ingress TCP port 80 is allowed in your Security List."
warn "On 1 GB RAM, keep sentiment_backend=openrouter or mock in config/dev.yaml (not finbert)."
echo ""