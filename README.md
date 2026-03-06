# AI Trading Platform — Forex & Gold

Industrial-standard algorithmic trading platform for Forex (EUR/USD, GBP/USD, USD/JPY) and Gold. Built in phases: data → features → models → backtest → execution → paper → live.

## Quick start

### Prerequisites

- Python 3.10+
- Optional: copy `.env.example` to `.env` and set `ENV`, `CONFIG_DIR`; add broker keys only for live trading.

### Install

```bash
cd trading-platform
pip install -e ".[dev]"
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

### Backtest (when implemented)

```bash
python scripts/run_backtest.py
```

## Project layout

| Path | Purpose |
|------|---------|
| `config/` | Env-specific YAML config (no secrets) |
| `src/` | Source: data, features, models, backtest, execution |
| `tests/` | Unit, integration, e2e |
| `scripts/` | Train, backtest, paper, retrain |
| `docs/` | ADRs, runbooks |

See **MAIN-IMPLEMENTATION-PLAN.md** (in parent `pr1/` directory) for the full roadmap.

## Docs

- [ADR-001: Why CPCV](docs/ADR-001-cpcv.md)
- [ADR-002: Config schema](docs/ADR-002-config.md)
- [Data versioning](docs/data-versioning.md)
- [Data sources](docs/data-sources.md)
- Runbooks: [halt trading](docs/runbook-halt-trading.md), [deploy](docs/runbook-deploy.md)

## License

MIT
