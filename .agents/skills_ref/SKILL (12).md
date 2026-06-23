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
# Division 4 — contracts and bus
PYTHONPATH=src CONFIG_DIR=$(pwd)/config pytest tests/unit/test_contracts.py tests/unit/test_clock.py tests/unit/test_bus.py -v --tb=short

# Division 1 — data layer
PYTHONPATH=src CONFIG_DIR=$(pwd)/config pytest tests/unit/test_schema.py tests/unit/test_ohlcv_store.py tests/unit/test_gateway_replay.py tests/integration/test_scheduler.py -v --tb=short

# Division 2 — fundamental analysis
PYTHONPATH=src CONFIG_DIR=$(pwd)/config pytest tests/unit/test_finbert.py tests/unit/test_aggregator.py tests/integration/test_fa_engine.py -v --tb=short

# Division 3 — technical analysis
PYTHONPATH=src CONFIG_DIR=$(pwd)/config pytest tests/unit/test_indicators.py tests/unit/test_confluence.py tests/integration/test_ta_engine.py -v --tb=short

# Division 5 — decision engine
PYTHONPATH=src CONFIG_DIR=$(pwd)/config pytest tests/unit/test_fusion.py tests/unit/test_risk_gate.py tests/integration/test_de_engine.py -v --tb=short

# Division 6 — execution
PYTHONPATH=src CONFIG_DIR=$(pwd)/config pytest tests/unit/test_sim_broker.py tests/unit/test_circuit_breaker.py tests/integration/test_execution.py -v --tb=short

# Division 7 — notifications
PYTHONPATH=src CONFIG_DIR=$(pwd)/config pytest tests/unit/test_formatters.py tests/unit/test_filters.py tests/integration/test_notifier.py -v --tb=short

# Division 8 — model training
PYTHONPATH=src CONFIG_DIR=$(pwd)/config pytest tests/unit/test_feature_builder.py tests/unit/test_label_builder.py tests/integration/test_pipeline.py -v --tb=short

# Division 9 — replay
PYTHONPATH=src CONFIG_DIR=$(pwd)/config pytest tests/unit/test_scorer.py tests/integration/test_replay_automated.py tests/integration/test_replay_manual.py -v --tb=short
```

### Single test file or test name
```bash
PYTHONPATH=src CONFIG_DIR=$(pwd)/config pytest tests/unit/test_contracts.py -v
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
