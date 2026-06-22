# AITrader — Master Architecture Plan

## Vision
Modular algorithmic trading platform for Forex and Gold, extensible to any instrument.
Three analytical pillars (Fundamental, Technical, Decision) backed by clean data infrastructure,
paper-to-live execution, professional web UI, and offline training/backtesting tooling.

**Initial instruments:** EUR/USD, GBP/USD, USD/JPY, XAU/USD
**Timeframes:** 1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w

---

## Division Map

| ID  | Short Name  | Full Role |
|-----|-------------|-----------|
| D01 | CORE        | Shared contracts, signal bus, virtual clock |
| D02 | DATA        | All data ingestion, normalization, storage |
| D03 | FUNDAMENTAL | News sentiment, macro analysis, event classification |
| D04 | TECHNICAL   | Price indicators, multi-TF confluence, regime detection |
| D05 | DECISION    | Signal fusion, trade signal generation, LLM narrative |
| D06 | EXECUTION   | Order management, broker bridge, risk manager |
| D07 | NOTIFIER    | Telegram bot, alert routing, inbound commands |
| D08 | BACKTEST    | Automated backtest, strategy replay, manual replay |
| D09 | TRAINER     | Model training pipeline, evaluation, registry |
| D10 | WEBUI       | FastAPI backend, React frontend, Lightweight Charts |
| D11 | OPS         | Health checks, metrics, log aggregation |

Reference docs: `CONTRACTS.md` (all shared schemas), `MASTER.md` (this file)

---

## Dependency Graph

```
D01-CORE (no dependencies)
└── D02-DATA
      ├── D03-FUNDAMENTAL ──────────────┐
      │                                 ▼
      └── D04-TECHNICAL ──────────── D05-DECISION
                                         │
                                      D06-EXECUTION
                                         │
                                      D07-NOTIFIER (also subscribes to D03, D04)

D08-BACKTEST  ->  D01, D02, D04, D05, D06-SimBroker  (offline only, never live)
D09-TRAINER   ->  D01, D02, D04, D08                  (offline only, never live)
D10-WEBUI     ->  D01-bus (live signals), D02-store (history), D06-portfolio state
D11-OPS       ->  all divisions (read-only health endpoints)
```

Hard rule: no division imports from a division outside its declared dependency list.
D10 never imports from D03 or D04 directly — it reads their signals via the bus.
D08 and D09 never run in the same process as the live trading loop.

---

## Build Phases

### Phase 0 — Contract Design (no code, ~1 week)
Design all Pydantic models in CONTRACTS.md. Lock signal schemas, bus protocol,
VirtualClock interface. No implementation starts until contracts are signed off.

### Phase 1 — D01 + D02 (~2 weeks)
- D01: InProcessBus, VirtualClock (live mode), all Pydantic types, structured logging
- D02: OHLCV loaders, economic calendar, news ingestion, Parquet store, data scheduler
- Milestone: price bar emitted onto bus; calendar events stored and queryable

### Phase 2 — D04 + D08 (~3 weeks)
- D04: Refactor src/features/ -> emit typed TechnicalSignal; multi-TF confluence layer
- D08: Replay engine using VirtualClock; auto backtest (refactor existing CPCV/walk-forward)
- Milestone: replay 1 year EUR/USD with technical signals; manual buy/sell controls work

### Phase 3 — D03 + D07 (~3 weeks, parallel)
- D03: News fetcher, FinBERT scorer, event classifier, signal decay
- D07: Telegram bot subscriber, rate limiter, aggregator, inbound commands
- Milestone: Telegram receives alert when CPI/NFP news fires

### Phase 4 — D05 + D06 (~2 weeks)
- D05: Weighted signal fusion v1, expiry validation, OpenRouter narrative
- D06: Refactor src/execution/ to consume TradeSignal; economic calendar circuit breaker; mode gate
- Milestone: full paper trading loop driven by combined signals; Telegram reports trades

### Phase 5 — D10 (~3 weeks)
- FastAPI backend with WebSocket push; React + Lightweight Charts frontend
- Panels: live chart, signal log, news feed, portfolio stats, config editor, replay page
- Replace all Streamlit dashboards
- Milestone: live candlestick + signal overlays in browser

### Phase 6 — D09 (~2 weeks)
- LSTM training pipeline on combined F+T feature set
- CPCV validation before model promotion; rollback procedure
- Swap D05 from weighted combiner to trained model in staging
- Milestone: model in staging, evaluated against combiner baseline

### Phase 7 — D11 + Redis Bus (~2 weeks)
- Division health checks, bus latency metrics, data freshness alerts
- Swap InProcessBus -> RedisBus (one config line; no code changes in other divisions)
- Milestone: any division failure triggers OPS alert; multi-process deployment works

---

## Cross-Cutting Concerns

### Clock
All time access via VirtualClock.now() from D01.
datetime.utcnow(), datetime.now(), time.time() are BANNED outside src/core/clock.py.
In live mode: returns UTC now. In replay mode: returns current bar timestamp.
Only D08-BACKTEST calls clock control methods (set_replay_time, advance, reset_to_live).

### Signal Bus
Two implementations in D01, selected via core.bus_backend config:
- memory  -> InProcessBus (asyncio.Queue, default for dev and single-process)
- redis   -> RedisBus (Redis pub/sub, for multi-process production)
All divisions use only the Bus protocol interface; never instantiate a bus directly.

### Secrets
No secrets in YAML config files. Keys in .env only:
TELEGRAM_BOT_TOKEN, OPENROUTER_API_KEY, NEWSAPI_KEY, OANDA_API_KEY, FRED_API_KEY
See .env.example. Each division MD lists which env vars it requires.

### Logging
Structured JSON logging everywhere. Every log record includes: division, signal_id,
instrument, timestamp. signal_id flows through the full lifecycle (fetch -> signal -> trade -> fill).

### Instrument Config
Each instrument defined in config/instruments.yaml: pip size, lot size, session hours,
active timeframes, fundamental/technical weight split, max position size.

---

## Target Repo Structure

```
src/
  core/           <- D01
  data/           <- D02
  fundamental/    <- D03
  technical/      <- D04
  decision/       <- D05
  execution/      <- D06
  notifier/       <- D07
  backtest/       <- D08
  trainer/        <- D09
  api/            <- D10 backend
frontend/         <- D10 frontend (React)
config/
  instruments.yaml
  dev.yaml / staging.yaml / prod.yaml
data/
  raw/            <- OHLCV Parquet
  news/           <- news store
  models/         <- model registry
docs/
  MASTER.md / CONTRACTS.md / D01-CORE.md ... D11-OPS.md
```

---

## Coding Standards

- Linting: ruff E F I UP B C4; line length 100
- Type checking: mypy disallow_untyped_defs, warn_unused_ignores
- Test order in CI: ruff check -> ruff format -> mypy -> pytest
- Coverage gates: 50% default; 80% for D01-CORE and D06-EXECUTION
- No datetime.now() outside src/core/clock.py
- Signal IDs on every signal object; log them on every operation
- Fail loud: data fetch failures raise exceptions and surface to D11

---

## How to Read Division MDs

Each D0X-NAME.md covers:
1. Purpose and hard boundaries (what it does NOT do)
2. Dependencies
3. Emits / exposes
4. Internal module structure
5. Existing code to migrate
6. Testing strategy and coverage target
7. Implementation phases (internal to this division)
8. Known risks

Division numbers indicate logical layer, not build sequence.
Build sequence is defined here in MASTER.md phases above.
