# AI Trading Platform — Forex & Gold

Industrial-standard algorithmic trading platform for Forex (EUR/USD, GBP/USD, USD/JPY) and Gold. Built in phases: data → features → models → backtest → execution → paper → live.

## Features

- **Multi-Timeframe Analysis**: 1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w, 1mo timeframes
- **Real-Time Live Data**: Yahoo Finance integration for live market data
- **Paper Trading**: Realistic simulated trading with slippage & commissions
- **Professional Web UI**: React + TypeScript + TradingView Lightweight Charts dashboard (replaces Streamlit)
- **Hybrid AI Models**: LSTM + Transformer architecture
- **Production-Ready**: Circuit breakers, risk management, audit logging
- **Docker Support**: One-command containerized deployment

## Quick start

### Prerequisites

- Python 3.10+
- Node.js 18+ (for the Web UI)
- Optional: copy `.env.example` to `.env` and set `ENV`, `CONFIG_DIR`; add broker keys only for live trading.

### Install

```bash
cd AITrader
pip install -e ".[dev,live_data,dashboard]"
```

### Web UI (Active — replaces Streamlit)

The platform ships with a professional trading terminal built on **FastAPI + React + TypeScript + Vite**.

```bash
# Start the FastAPI backend (port 8000)
PYTHONPATH=src uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload

# In a separate terminal, start the React frontend (port 5173)
cd frontend
npm install
npm run dev

# Access the trading terminal
open http://localhost:5173
```

**API docs (auto-generated):**
```
open http://localhost:8000/docs
```

### Paper Trading (CLI)

```bash
# Start paper trading with live data (default: daily timeframe)
./scripts/start_paper.sh

# Different timeframes
./scripts/start_paper.sh --timeframe 5m --interval 300   # 5-min scalping
./scripts/start_paper.sh --timeframe 1h --interval 3600  # 1-hour intraday
./scripts/start_paper.sh --timeframe 4h --interval 14400 # 4-hour position

# Stop services
./scripts/stop_paper.sh

# Check status
./scripts/status_paper.sh
```

**See [docs/TIMEFRAMES.md](docs/TIMEFRAMES.md) for complete timeframe guide.**

### Docker Development (🐳)

Use Docker environment with local code for development:

```bash
# Build image (first time only)
./docker/docker_dev_build.sh

# Run tests in Docker
./docker/docker_dev_test.sh

# Interactive shell
./docker/docker_dev_shell.sh

# Paper trading
./docker/docker_dev_paper.sh --capital 100000
```

**See [docker/DOCKER-DEV-GUIDE.md](docker/DOCKER-DEV-GUIDE.md) for complete Docker development guide.**

### Docker Deployment

```bash
# Build and start all services
./docker/start_docker.sh --build

# Check status
./docker/status_docker.sh

# Stop
./docker/stop_docker.sh
```

### Run tests

```bash
PYTHONPATH=src CONFIG_DIR=$(pwd)/config pytest tests -v
```

**With real data:** Run `python scripts/download_sample_data.py` first to fetch EUR/USD, gold, etc. into `data/raw/`. Then `test_real_data_if_available` will validate those files.

### Config

- Config lives in **`config/`**. Use `config/dev.yaml`, `config/staging.yaml`, or `config/prod.yaml`.
- Set `ENV=dev` (default), `ENV=staging`, or `ENV=prod`.
- **No secrets in config files.** Use environment variables; see `.env.example`.

### Backtest

```bash
python scripts/run_backtest.py
```

## Project layout

| Path | Purpose |
|------|---------|
| `config/` | Env-specific YAML config (no secrets) |
| `src/core/` | Shared contracts, signal bus, clocks (D01) |
| `src/data/` | Data loaders, OHLCV store, schedulers (D02) |
| `src/technical/` | Technical indicators, confluence engine (D04) |
| `src/backtest/` | CPCV, walk-forward, replay sessions (D08) |
| `src/execution/` | Risk manager, circuit breaker, SimBroker |
| `src/api/` | FastAPI backend — REST + WebSocket (D10) |
| `frontend/` | React + TypeScript + Vite trading terminal (D10) |
| `tests/` | Unit, integration, e2e |
| `scripts/` | Train, backtest, paper, retrain |
| `docs/` | ADRs, runbooks |
| `DEV_PLAN/` | Division specs and project roadmap |

## Division Status

| Division | Name | Status |
|----------|------|--------|
| D01 | CORE | ✅ Complete |
| D02 | DATA | ✅ Complete |
| D03 | FUNDAMENTAL | 🔴 Phase 3 — Next |
| D04 | TECHNICAL | ✅ Complete |
| D05 | DECISION | 🔴 Phase 4 |
| D06 | EXECUTION | 🔴 Phase 4 |
| D07 | NOTIFIER | 🔴 Phase 3 — Next |
| D08 | BACKTEST | ✅ Complete |
| D09 | TRAINER | 🔴 Phase 6 |
| D10 | WEBUI | ✅ Complete |
| D11 | OPS | 🔴 Phase 7 |

See **[DEV_PLAN/STATUS_AND_ROADMAP.md](DEV_PLAN/STATUS_AND_ROADMAP.md)** for the full roadmap and division details.

## Docs

- **[Project Status & Roadmap](DEV_PLAN/STATUS_AND_ROADMAP.md)** — Division status, milestones, what's next
- **[Division Master Plan](DEV_PLAN/MASTER.md)** — Full architecture and build order
- **[Multi-Timeframe Guide](docs/TIMEFRAMES.md)** — Complete timeframe reference
- **[Go-Live Checklist](docs/go-live-checklist.md)** — Production deployment guide
- **[Docker Deployment](docker/README.md)** — Containerized deployment
- [ADR-001: Why CPCV](docs/ADR-001-cpcv.md)
- [ADR-002: Config schema](docs/ADR-002-config.md)
- [Data versioning](docs/data-versioning.md)
- [Data sources](docs/data-sources.md)
- Runbooks: [halt trading](docs/runbook-halt-trading.md), [deploy](docs/runbook-deploy.md)

## License

MIT
