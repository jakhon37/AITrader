---
name: backtest-run
description: Use this skill when starting a backtest, running a replay session, launching paper trading, running walk-forward validation, starting manual trading replay to test strategy skills, or interpreting backtest results and metrics.
---

# backtest-run

Runs backtests, replay sessions, and paper trading with correct arguments and environment.

## Paper trading (live signals, simulated orders)

```bash
# Default — uses primary timeframe from config
./scripts/start_paper.sh

# With explicit capital
./scripts/start_paper.sh --capital 10000

# Specific timeframe
./scripts/start_paper.sh --timeframe 1h --interval 3600

# Stop paper trading
./scripts/stop_paper.sh

# Check status
./scripts/status_paper.sh
```

Or via Docker:
```bash
./docker/docker_dev_paper.sh --capital 10000
```

## Automated backtest (headless, full speed)

```bash
PYTHONPATH=src CONFIG_DIR=$(pwd)/config python scripts/run_backtest.py \
  --instrument EURUSD \
  --start 2022-01-01 \
  --end 2023-12-31 \
  --timeframe 1h \
  --capital 10000
```

Results are saved to `data/backtest_results/{timestamp}_{instrument}/`.

## Replay session (via API — requires Division 10 running)

Start the API server first:
```bash
PYTHONPATH=src CONFIG_DIR=$(pwd)/config uvicorn api.app:app --reload --port 8000
```

Then start a replay session:
```bash
# AUTOMATED mode — watch model trade
curl -X POST http://localhost:8000/api/replay/start \
  -H "Content-Type: application/json" \
  -d '{
    "instrument": "EURUSD",
    "start_date": "2023-01-01",
    "end_date": "2023-06-01",
    "mode": "automated",
    "speed": 50.0
  }'

# WATCH mode — same as automated, different UI label
curl -X POST http://localhost:8000/api/replay/start \
  -d '{"instrument": "XAUUSD", "start_date": "2023-06-01", "end_date": "2023-12-31", "mode": "watch", "speed": 20.0}'

# MANUAL mode — you make all trading decisions
curl -X POST http://localhost:8000/api/replay/start \
  -d '{"instrument": "EURUSD", "start_date": "2023-03-01", "end_date": "2023-06-01", "mode": "manual", "speed": 0}'
```

Control a running session:
```bash
SESSION_ID="your-session-id-here"

# Pause
curl -X POST http://localhost:8000/api/replay/control \
  -d "{\"session_id\": \"$SESSION_ID\", \"action\": \"pause\"}"

# Resume
curl -X POST http://localhost:8000/api/replay/control \
  -d "{\"session_id\": \"$SESSION_ID\", \"action\": \"resume\"}"

# Step one bar forward (manual/watch mode)
curl -X POST http://localhost:8000/api/replay/control \
  -d "{\"session_id\": \"$SESSION_ID\", \"action\": \"step\"}"

# Change speed
curl -X POST http://localhost:8000/api/replay/control \
  -d "{\"session_id\": \"$SESSION_ID\", \"action\": \"speed\", \"value\": 100}"
```

Submit a manual trade (MANUAL mode only):
```bash
curl -X POST http://localhost:8000/api/replay/trade \
  -d "{
    \"session_id\": \"$SESSION_ID\",
    \"direction\": \"BULLISH\",
    \"size\": 0.1,
    \"stop_loss\": 1.0850,
    \"take_profit\": 1.0980
  }"
```

## Walk-forward validation

```bash
PYTHONPATH=src CONFIG_DIR=$(pwd)/config python -c "
from backtest.walk_forward import WalkForwardRunner
from config import AppConfig
config = AppConfig.from_env()
runner = WalkForwardRunner(config)
results = runner.run(instrument='EURUSD', n_windows=5, train_months=12, test_months=3)
print(results.summary())
"
```

## Interpreting backtest results

Key metrics and what they mean:

| Metric | Good | Acceptable | Bad |
|---|---|---|---|
| Sharpe ratio | > 1.5 | 0.5 – 1.5 | < 0.5 |
| Win rate | > 55% | 45–55% | < 45% |
| Profit factor | > 1.5 | 1.0–1.5 | < 1.0 |
| Max drawdown | < 10% | 10–20% | > 20% |
| Avg R:R | > 1.5 | 1.0–1.5 | < 1.0 |

**Warning signs in results:**
- Win rate > 70% with low Sharpe → likely overfit, check CPCV spread
- Sharpe looks good but max drawdown > 25% → position sizing too aggressive
- Profit factor < 1.0 → system loses money in aggregate, do not promote
- Large performance gap between train and test windows → overfit

## Result files

```
data/backtest_results/{timestamp}_{instrument}/
├── summary.md          ← human-readable report
├── trades.csv          ← every trade: entry/exit/P&L/signal_id
├── equity_curve.parquet ← timestamp → equity value
├── metrics.json        ← all numeric metrics
└── signals.parquet     ← all signals emitted during the run
```

## Minimum requirements before live trading

1. Run backtest on out-of-sample data (not used in training) for at least 6 months
2. Run walk-forward with at least 4 windows — all windows Sharpe > 0.5
3. Run paper trading for at least 2 weeks — performance consistent with backtest
4. Max drawdown in paper trading < 15%
5. Get model promoted from staging to prod (see `promote-model` skill)
