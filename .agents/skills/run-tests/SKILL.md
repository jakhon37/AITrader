---
name: run-tests
description: Use this skill when the user wants to run tests, check coverage, run CI checks, run pytest, run linting with ruff, run mypy, or verify a division passes its test gate before marking it complete.
---

# run-tests

Runs the correct test command for the AITrader project with all required environment variables and path setup.

## Environment requirements

Always set these before running pytest:
```bash
export PYTHONPATH=src
export CONFIG_DIR=$(pwd)/config
export ENV=dev
```

## Commands by scope

### Full suite (all divisions)
```bash
PYTHONPATH=src CONFIG_DIR=$(pwd)/config pytest tests -v --tb=short --cov=src --cov-report=term-missing --cov-fail-under=50
```

### Single division
```bash
# Division 1 — Core, contracts, bus, IDs
PYTHONPATH=src CONFIG_DIR=$(pwd)/config pytest tests/unit/test_core.py -v --tb=short

# Division 2 — Data loader & Parquet store
PYTHONPATH=src CONFIG_DIR=$(pwd)/config pytest tests/unit/test_csv_loader.py tests/unit/test_data_store.py tests/unit/test_data_sources.py tests/unit/test_data_scheduler.py tests/unit/test_data_retention.py tests/integration/test_data_pipeline.py -v --tb=short

# Division 3 — Fundamental analysis
PYTHONPATH=src CONFIG_DIR=$(pwd)/config pytest tests/unit/test_fundamental.py -v --tb=short

# Division 4 — Technical analysis & confluence
PYTHONPATH=src CONFIG_DIR=$(pwd)/config pytest tests/unit/test_technical.py tests/unit/test_technical_indicators.py tests/unit/test_regime_detector.py -v --tb=short

# Division 5 — Decision engine
PYTHONPATH=src CONFIG_DIR=$(pwd)/config pytest tests/unit/test_decision.py -v --tb=short

# Division 6 — Execution & Risk Manager
PYTHONPATH=src CONFIG_DIR=$(pwd)/config pytest tests/unit/test_api_replay.py tests/integration/test_execution.py tests/unit/test_backtest_engine.py -v --tb=short

# Division 7 — Notifications & Telegram Notifier
PYTHONPATH=src CONFIG_DIR=$(pwd)/config pytest tests/unit/test_notifier.py -v --tb=short

# Division 8 — Backtest and Replay
PYTHONPATH=src CONFIG_DIR=$(pwd)/config pytest tests/unit/test_backtest_feed.py tests/unit/test_backtest_replay.py tests/integration/test_backtest_e2e.py -v --tb=short

# Division 9 — ML Trainer & Models
PYTHONPATH=src CONFIG_DIR=$(pwd)/config pytest tests/unit/test_ensemble.py tests/unit/test_garch_gru.py tests/unit/test_lstm_transformer.py tests/unit/test_meta_labeler.py tests/unit/test_model_registry.py tests/integration/test_model_pipeline.py -v --tb=short
```

### Single test file or test name
```bash
PYTHONPATH=src CONFIG_DIR=$(pwd)/config pytest tests/unit/test_core.py -v
PYTHONPATH=src CONFIG_DIR=$(pwd)/config pytest tests/integration/test_execution.py::test_trade_signal_to_fill -v
```

### Lint and type check (run before any commit)
```bash
# Lint
ruff check src tests scripts

# Format check (does not modify files)
ruff format --check src tests scripts

# Type check (ignore missing stubs for torch/xgboost/lightgbm/arch)
mypy src
```

### Fix lint issues automatically
```bash
ruff check --fix src tests scripts
ruff format src tests scripts
```

## Coverage gates per division

| Division | Minimum coverage |
|----------|-----------------|
| 4 (contracts/bus) | 80% |
| 1 (data) | 70% |
| 2 (fundamental) | 65% |
| 3 (technical) | 70% |
| 5 (decision) | 70% |
| 6 (execution) | 70% |
| 7 (notifications) | 70% |
| 8 (training) | 65% |
| 9 (replay) | 65% |
| 10 (api backend) | 65% |
| 11 (monitoring) | 70% |

## Docker test runner (alternative)
```bash
./docker/docker_dev_test.sh
```
Docker sets `PYTHONPATH=/app/src` and `CONFIG_DIR=/app/config` automatically.

## Before marking a division COMPLETE

Run this checklist in order:
1. `ruff check src tests scripts` — must be clean
2. `ruff format --check src tests scripts` — must be clean
3. `mypy src` — internal code clean (ignore external import errors)
4. `pytest tests -v` for the division — all green
5. Coverage meets division minimum
6. Update division MD status line to `Status: COMPLETE`
