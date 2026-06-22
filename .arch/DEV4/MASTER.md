# AITrader — Master Architecture Plan

## Revision note
This version fixes six gaps found in the prior pass: D08 and D09 were missing a D03
dependency (full-system replay and combined-feature training both need fundamental
data, not just technical), D06 had no wired source for the economic-calendar circuit
breaker, D10 was missing D08 (the replay page has to control something), D07's graph
notation looked like a direct import instead of a bus subscription, and the D09→D05
model handoff was never specified. All six are fixed below.

## Vision
Modular algorithmic trading platform for Forex and Gold, extensible to any instrument.
Three analytical pillars (Fundamental, Technical, Decision) backed by clean data infrastructure,
paper-to-live execution, professional web UI, and offline training/backtesting tooling.

**Initial instruments:** EUR/USD, GBP/USD, USD/JPY, XAU/USD (Gold)
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
              D02 (calendar) ──────► D06-EXECUTION
                                         │
                                      D07-NOTIFIER
                  (bus-only subscriber: consumes D02/D03/D04/D05/D06
                   emissions via D01's bus. Never imports those divisions
                   directly — this is a hard rule, not a convenience.)

D08-BACKTEST  →  D01, D02, D03, D04, D06-SimBroker
                  (offline only, never live. D03 wiring lands in Phase 3 —
                   Phase 2's replay milestone is technical-only by necessity,
                   since D03 doesn't exist yet at that point in the build.)

D09-TRAINER   →  D01, D02, D03, D04, D08
                  (offline only, never live. Same D03-in-Phase-3 caveat as D08.)

  D09 writes model artifacts + metadata to D02's registry store (data/models/).
  D05 reads that store directly at startup/reload to pick up new models.
  This is an ARTIFACT dependency, not a runtime one — D05 never imports D09,
  and D09 never runs inside the live process. The registry file is the only
  contract between them.

D10-WEBUI     →  D01-bus (live signals), D02-store (history),
                  D06 (portfolio/fill state), D08 (replay control, replay page only)
D11-OPS       →  all divisions (read-only health endpoints; explicit exception
                  to the no-cross-import rule, since OPS exists to observe, not act)
```

**Hard rule:** no division imports from a division outside its declared dependency list.
D10 never imports from D03 or D04 directly — it reads their signals via the bus (D01).
D07 never imports from D02/D03/D04/D05/D06 — same rule, bus only.
D08 and D09 never run in the same process as the live trading loop.

---

## Build Phases

### Phase 0 — Contract Design (no code, ~1 week)
Design all Pydantic models documented in `CONTRACTS.md`. Lock signal schemas, bus protocol,
VirtualClock interface, registry artifact format (since D09/D05 depend on its shape).
No implementation starts until contracts are reviewed and signed off.

### Phase 1 — D01 + D02 (~2 weeks)
- D01: InProcessBus, VirtualClock (live mode), all Pydantic types, structured logging
- D02: OHLCV loaders (refactor existing csv_loader + live_data), economic calendar,
  news ingestion, Parquet store, data scheduler (fires candle-close events onto bus)
- **Milestone:** price bar emitted onto bus; calendar events stored and queryable

### Phase 2 — D04 + D08 (~3 weeks, D08 starts 1 week after D04)
- D04: Refactor `src/features/` → emit typed `TechnicalSignal`. Multi-TF confluence layer.
- D08: Replay engine using VirtualClock. Automated backtest (refactor existing CPCV/walk-forward).
  Manual replay mode with human trade entry. **Technical-only scope at this phase** — D03
  doesn't exist yet, so fundamental replay is a Phase 3 follow-on, not a Phase 2 gap.
- **Milestone:** replay 1 year EUR/USD with technical signals; manual buy/sell controls work

### Phase 3 — D03 + D07 (~3 weeks, parallel)
- D03: News fetcher, FinBERT scorer, event classifier, signal decay logic
- D07: Telegram bot subscriber, rate limiter, message aggregator, inbound command handler
- D08: extend replay to include fundamental signal playback now that D03 exists
- D09: extend feature pipeline to include fundamental features now that D03 exists
- **Milestone:** Telegram receives alert when CPI/NFP news fires; replay shows F+T together

### Phase 4 — D05 + D06 (~2 weeks)
- D05: Weighted signal fusion v1, expiry validation, async OpenRouter narrative
- D06: Refactor `src/execution/` to consume `TradeSignal`. Economic calendar circuit breaker
  (reads D02's calendar store directly — see dependency graph). Hard paper/live mode gate.
- **Milestone:** full paper trading loop driven by combined F+T signals; Telegram reports trades

### Phase 5 — D10 (~3 weeks)
- FastAPI backend with WebSocket push
- React + Lightweight Charts frontend
- Panels: live chart, signal log, news feed, portfolio stats, config editor, replay page
  (replay page proxies play/pause/step/speed commands to D08's replay engine)
- Replace all Streamlit dashboards
- **Milestone:** live candlestick + signal overlays in browser; Streamlit decommissioned

### Phase 6 — D09 (~2 weeks)
- LSTM training pipeline on combined F+T feature set (D03 + D04 features)
- CPCV validation before model promotion (uses D08)
- Rollback procedure for underperforming models
- Writes promoted model to registry store; D05 picks it up on next reload
- **Milestone:** model in staging, evaluated against weighted combiner baseline

### Phase 7 — D11 + Redis Bus (~2 weeks)
- D11: division health checks, bus latency metrics, data freshness alerts, model drift monitoring
- Swap InProcessBus → RedisBus (one config line change; no code changes in other divisions)
- **Milestone:** any division failure triggers OPS alert; multi-process deployment works

---

## Cross-Cutting Concerns

### Clock
All current-time access must go through `VirtualClock.now()` from D01.
`datetime.utcnow()`, `datetime.now()`, and `time.time()` are **banned** outside `src/core/clock.py`.
In live mode the clock returns UTC now. In replay mode it returns the current bar's timestamp.
Only D08-BACKTEST calls the clock control methods (`set_replay_time`, `advance`, `reset_to_live`).
When D10's replay page drives a replay session, it calls D08's API, which calls the clock —
the UI never touches VirtualClock directly.

### Signal Bus
Two implementations in D01, selected via `core.bus_backend` config:
- `memory` → InProcessBus (asyncio.Queue, default for dev and single-process)
- `redis` → RedisBus (Redis pub/sub, for multi-process production)
All divisions use only the `Bus` protocol interface — never instantiate a bus directly.
The bus instance is injected at startup from the app's composition root.

### Model Artifact Handoff (D09 → D05)
D09 never runs live and D05 never imports D09. The registry directory (`data/models/`,
owned by D02's storage layer) is the only contract between them: D09 writes versioned
artifacts + metadata JSON on promotion, D05 polls or reloads on signal to pick up a new
model. See `CONTRACTS.md` for the registry metadata schema.

### Safety Gates
`execution.mode` (`paper` | `live`) is a hard config flag in D06. Switching to `live`
requires a second explicit check — an environment variable plus a startup confirmation —
never a bare YAML edit. This is non-negotiable given Phase 4 is where real broker
credentials first become reachable from the codebase.

### Secrets
No secrets in YAML config files. Keys in `.env` only:
`TELEGRAM_BOT_TOKEN`, `OPENROUTER_API_KEY`, `NEWSAPI_KEY`, `OANDA_API_KEY`, `FRED_API_KEY`.
See `.env.example`. Each division MD lists which env vars it requires.

### Logging
Structured JSON logging everywhere using Python `structlog` or `logging` with JSON formatter.
Every log record includes: `division`, `signal_id` (correlation), `instrument`, `timestamp`.
`signal_id` flows through all log entries for a signal's full lifecycle (fetch → signal → trade → fill).
D11 aggregates and queries these logs.

### Instrument Config
Each instrument defined in `config/instruments.yaml`: pip size, lot size, session hours,
active timeframes, fundamental/technical weight split, max position size.
All divisions load instrument config via `src.core.config.InstrumentConfig`.

---

## Target Repo Structure

```
src/
  core/           ← D01 (new; replaces top-level src/config.py)
  data/           ← D02 (refactor existing src/data/)
  fundamental/    ← D03 (new)
  technical/      ← D04 (refactor existing src/features/)
  decision/       ← D05 (new)
  execution/      ← D06 (refactor existing src/execution/)
  notifier/       ← D07 (new)
  backtest/       ← D08 (refactor existing src/backtest/)
  trainer/        ← D09 (new; absorbs model training from src/models/)
  api/            ← D10 backend (refactor existing src/api/ placeholder)
frontend/         ← D10 frontend (new React app)
config/
  instruments.yaml
  dev.yaml
  staging.yaml
  prod.yaml
data/
  raw/            ← OHLCV Parquet files
  news/           ← news article store
  models/         ← model registry (existing, written by D09, read by D05)
docs/
  MASTER.md       ← this file
  CONTRACTS.md    ← schema reference (read before touching any signal)
  D01-CORE.md
  D02-DATA.md
  D03-FUNDAMENTAL.md
  D04-TECHNICAL.md
  D05-DECISION.md
  D06-EXECUTION.md
  D07-NOTIFIER.md
  D08-BACKTEST.md
  D09-TRAINER.md
  D10-WEBUI.md
  D11-OPS.md
```

---

## Coding Standards

Inherited from AGENTS.md, with additions:

- **Linting:** ruff selects `E F I UP B C4`; line length 100; `E501` ignored
- **Type checking:** mypy `disallow_untyped_defs`, `warn_unused_ignores`
- **Test order in CI:** ruff check → ruff format → mypy → pytest
- **Coverage gates:** 50% default; 80% for D01-CORE and D06-EXECUTION (critical path)
- **Env vars:** `PYTHONPATH=src`, `CONFIG_DIR=$(pwd)/config` in all test runs
- **No secrets** in YAML, code, or committed files
- **No `datetime.now()`** outside `src/core/clock.py` — enforced by ruff custom rule or pre-commit hook
- **Signal IDs** on every signal object; log them on every operation touching that signal
- **Fail loud:** data fetch failures raise exceptions and surface to D11; never silently return empty data

---

## How to Read Division MDs

Each `D0X-NAME.md` covers in order:
1. Purpose (2–3 sentences) and hard boundaries (what it does NOT do)
2. Dependencies — which divisions it imports from
3. Emits / exposes — what it puts on the bus or exposes as a direct API
4. Internal module structure with file-level descriptions
5. Existing code to migrate (where applicable)
6. Testing strategy and coverage target
7. Implementation phases (internal to this division)
8. Known risks and gotchas

Division numbers indicate **logical layer**, not build sequence.
Build sequence is defined here in MASTER.md phases above — follow phases, not division numbers.
