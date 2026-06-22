# AITrader Project Status & Roadmap

## Executive Summary
AITrader is being refactored and built following a modular multi-division plan (`DEV_PLAN/MASTER.md`). 
- **Completed Phases**: Phase 0 (Contract Design), Phase 1 (D01-CORE + D02-DATA), and **Phase 2 (D04-TECHNICAL + D08-BACKTEST)** are fully completed and verified.
- **Current Phase**: We are ready to start **Phase 3 (D03-FUNDAMENTAL + D07-NOTIFIER)**.
- **Test Suite Status**: Ran the test suite via Docker (`./docker/docker_dev_test.sh`). **405 out of 405 tests passed (100% success)**.
- **Bugs Fixed**: Resolved the vectorized `BacktestEngine` bug by ensuring open positions are force-closed on the last bar of a backtest run.
- **Features Implemented**: Completed Phase 2b replay architecture, including `session_state.py`, `replay.py`, `scorer.py`, `reporter.py`, and `websocket.py` (stub).

---

## Status by Division

| Division | Name | Role | Status | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **D01** | **CORE** | Shared contracts, signal bus, clocks | **100% Completed** | [src/core/](file:///Users/mac37/workspace/TRADE/AITrader/src/core) is active. |
| **D02** | **DATA** | Data loaders, stores, schedulers | **100% Completed** | [src/data/](file:///Users/mac37/workspace/TRADE/AITrader/src/data) is active with sqlite news/calendar layer. |
| **D03** | **FUNDAMENTAL** | FinBERT sentiment, macro regime | **Not Started** | Scheduled for Phase 3. |
| **D04** | **TECHNICAL** | Technical indicators, confluence | **100% Completed** | [src/technical/](file:///Users/mac37/workspace/TRADE/AITrader/src/technical) refactored from `src/features/`. |
| **D05** | **DECISION** | Signal fusion, LLM narratives | **Not Started** | Scheduled for Phase 4. |
| **D06** | **EXECUTION** | Order/risk management, SimBroker | **Not Started** | Scheduled for Phase 4. (Old wrapper exists). |
| **D07** | **NOTIFIER** | Telegram bot, alert routing | **Not Started** | Scheduled for Phase 3 (Parallel). |
| **D08** | **BACKTEST** | CPCV, walk-forward, strategy replay | **100% Completed** | Refactored engine, added feeds, watch/manual sessions, scoring scorecard, and interactive HTML reporting. |
| **D09** | **TRAINER** | Model training pipelines | **Not Started** | Scheduled for Phase 6 (Old codebase models present). |
| **D10** | **WEBUI** | FastAPI & React frontend dashboard | **Not Started** | Scheduled for Phase 5. |
| **D11** | **OPS** | Health metrics & logger | **Not Started** | Scheduled for Phase 7. |

---

## Completed Implementations (Phase 2b)

### 1. Vectorized Backtest Auto-Close Fix
Fixed [src/backtest/engine.py](file:///Users/mac37/workspace/TRADE/AITrader/src/backtest/engine.py) to force-close any open position on the last historical bar, preventing empty trade results for buy-and-hold signals.

### 2. Thread-Safe Session State
Created [src/backtest/session_state.py](file:///Users/mac37/workspace/TRADE/AITrader/src/backtest/session_state.py) to track active replay metrics (position summaries, current virtual clock time, speed, status, and portfolio state) thread-safely.

### 3. Strategy & Manual Replay Engines
Created [src/backtest/replay.py](file:///Users/mac37/workspace/TRADE/AITrader/src/backtest/replay.py):
- **StrategyReplaySession**: Streams chronological market bars with real-time speed adjustments, pause/resume controls, and publishes to the isolated bus for validation of technical model decisions.
- **ManualReplaySession**: Deactivates automated signal triggers, allowing human trading step-by-step. Orders are processed via the isolated bus by `SimBroker` / `MockExecutionEngine`.

### 4. Replay Scorer
Created [src/backtest/scorer.py](file:///Users/mac37/workspace/TRADE/AITrader/src/backtest/scorer.py) to compute performance scorecards containing net profit, win rate, average risk-to-reward ratio, maximum drawdown, and a **discipline score** checking if the manual entries respected their stop-losses.

### 5. Interactive HTML & JSON Reporter
Created [src/backtest/reporter.py](file:///Users/mac37/workspace/TRADE/AITrader/src/backtest/reporter.py) to export:
- Performance scorecard JSON.
- Clean console log summary tables.
- Modern, interactive HTML reports with dark styling utilizing **Chart.js** CDN for responsive equity curves and trade win/loss distribution charts.
- Included an auto-cleanup retention policy preserving only the last 50 files.

---

## What is Next?

### Phase 3 Execution (Fundamental & Notifier)
Start implementation of:
1. **D03-FUNDAMENTAL**: News FinBERT sentiment agent, macro regime classifications, and OpenRouter prompt narration templates ([D03-FUNDAMENTAL.md](file:///Users/mac37/workspace/TRADE/AITrader/DEV_PLAN/D03-FUNDAMENTAL.md)).
2. **D07-NOTIFIER**: Telegram bot alerting and command parsing integration ([D07-NOTIFIER.md](file:///Users/mac37/workspace/TRADE/AITrader/DEV_PLAN/D07-NOTIFIER.md)).
3. **D08 Wire-in**: Extend `StrategyReplaySession` to initialize and subscribe `FundamentalAgent` signals once Phase 3 is completed.
