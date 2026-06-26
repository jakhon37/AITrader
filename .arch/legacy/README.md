# Legacy Code Archive

Superseded modules moved out of `src/` during the D01–D11 division migration.

| Path | Replaced by |
|------|-------------|
| `src/features/` | `src/technical/` + `src/trainer/feature_engine.py` |
| `src/config.py` | `src/core/config.py` |
| `src/visualization/` | D10 Web UI (`frontend/`) + `src/backtest/reporter/` |
| `src/models/` | `src/trainer/models/` |
| `dashboards/` (Streamlit) | D10 Web UI (`frontend/`, `src/api/`) |
| `scripts/start_paper.sh`, `stop_paper.sh` | `scripts/start_webui.sh`, `stop_webui.sh` |
| `*_legacy.py` (backtest/data) | Refactored modules under `src/backtest/`, `src/data/` |

Do not import from this directory in production code. Reference only.