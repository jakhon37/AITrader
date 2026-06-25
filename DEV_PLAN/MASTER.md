# AITrader — Master Architecture Plan

## Revision note
This version reconciles MASTER.md with the detailed division docs, which had drifted
ahead of it. Three things were fixed here that the division docs either already handled
better than this file documented, or hadn't documented at all:
- D08 and D09 now show D03-FUNDAMENTAL as a phased dependency (available from Phase 3),
  matching the fix already applied in their own division MDs.
- The D09 → D05 model handoff is now stated explicitly as an artifact-only dependency
  (registry file on disk, no runtime coupling) — this existed implicitly in both
  division docs but was never written down anywhere as a stated design rule.
- The bus topic design (`BusChannel` enum, instrument carried as a field rather than
  encoded in hierarchical topic strings) is now described accurately per CONTRACTS.md,
  replacing this file's earlier dot-path topic-naming convention which the actual
  contracts never implemented.
The D06↔D02 calendar dependency, D10↔D08 replay control dependency, and D07's bus-only
wording were already correct in the division docs — this file just catches up to them.

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
        D02 (bus: ECONOMIC_EVENT, ──► D06-EXECUTION
             OHLCV_BAR)                 │
                                      D07-NOTIFIER
                  (bus-only subscriber: consumes D02/D03/D04/D05/D06 emissions
                   via D01's BusChannel. Never imports those divisions directly.)

D08-BACKTEST  →  D01, D02, D03*, D04, D05, D06-SimBroker
                  (offline only, never live. D03 is phased — D08's own build starts
                   in Phase 2, before D03 exists; Phase 2's replay milestone is
                   technical-only by necessity. D03 is wired into the isolated replay
                   bus in a Phase 3 follow-on once it ships. D08 also imports D05's
                   DecisionEngine directly, not just D04 — replay needs fused trade
                   signals, not raw technical signals, for the replay UI and manual
                   trading mode to make sense.)

D09-TRAINER   →  D01, D02, D03*, D04, D08
                  (offline only, never live. Same D03-phased caveat as D08 — D09's
                   feature pipeline combines D04 indicators with D03 sentiment scores,
                   reconstructed historically against D02's news store rather than via
                   live bus subscription, since there's no bus to subscribe to offline.)

  D09 writes ModelArtifact records (per CONTRACTS.md) to the registry store at
  data/models/registry.json. D05 reads that file directly to select the active prod
  model for fusion v2. This is an ARTIFACT dependency, not a runtime one — D05 never
  imports D09, D09 never imports D05, and D09 never runs inside the live process.
  The registry file is the only contract between them.

D10-WEBUI     →  D01-bus (live signals), D02-store (history),
                  D06 (portfolio/fill state), D08 (replay session control API)
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
Design all Pydantic models documented in `CONTRACTS.md`. Lock signal schemas, the
`BusChannel` enum and `Bus` protocol, the `VirtualClock`/`ControllableClock` interface,
and the `ModelArtifact` registry schema (since D09 and D05 both depend on its shape
even though neither imports the other). No implementation starts until contracts are
reviewed and signed off.

### Phase 1 — D01 + D02 (~2 weeks)
- D01: InProcessBus, VirtualClock (live mode), all Pydantic types, structured logging
- D02: OHLCV loaders (refactor existing csv_loader + live_data), economic calendar,
  news ingestion, Parquet store, data scheduler (publishes `OHLCV_BAR` and
  `ECONOMIC_EVENT` onto the bus)
- **Milestone:** price bar emitted onto bus; calendar events stored and queryable

### Phase 2 — D04 + D08 (~3 weeks, D08 starts 1 week after D04)
- D04: Refactor `src/features/` → emit typed `TechnicalSignal`. Multi-TF confluence layer.
- D08: Replay engine using `ControllableClock`. Automated backtest (refactor existing
  CPCV/walk-forward). Manual replay mode with human trade entry. Isolated replay bus
  instantiates D04 + D05 + D06-SimBroker locally — **D03 doesn't exist yet, so D05
  always sees fundamental=None during this phase's milestone.** That's expected, not
  a gap; D05's fusion already handles a missing fundamental signal gracefully.
- **Milestone:** replay 1 year EUR/USD with technical signals; manual buy/sell controls work

### Phase 3 — D03 + D07 (~3 weeks, parallel)
- D03: News fetcher, FinBERT scorer, event classifier, signal decay logic
- D07: Telegram bot subscriber, rate limiter, message aggregator, inbound command handler
- D08 follow-on: wire D03's FundamentalAgent into the isolated replay bus (fed from D02's
  historical news/calendar store rather than live polling); confirm replayed
  `FundamentalSignal` events now influence D05's fused output
- D09 follow-on: extend the feature pipeline to include D03's sentiment scores,
  reconstructed historically the same way D08 does
- **Milestone:** Telegram receives alert when CPI/NFP news fires; replay shows
  fundamental + technical signals together, matching what live trading will look like

### Phase 4 — D05 + D06 (~2 weeks)
- D05: Weighted signal fusion v1, expiry validation, async OpenRouter narrative
- D06: Refactor `src/execution/` to consume `TradeSignal`. Economic calendar circuit
  breaker (subscribes to `ECONOMIC_EVENT` from D02 — pre-release activation, post-release
  deactivation, scoped to `affected_pairs` only). Hard paper/live mode gate
  (`LIVE_TRADING_CONFIRMED` must be set in the shell, never `.env`).
- **Milestone:** full paper trading loop driven by combined F+T signals; Telegram reports trades

### Phase 5 — D10 (~3 weeks)
- FastAPI backend with WebSocket push
- React + Lightweight Charts frontend
- Panels: live chart, signal log, news feed, portfolio stats, config editor, replay page
  (replay page proxies play/pause/step/speed/manual-order commands to D08's replay API)
- Replace all Streamlit dashboards
- **Milestone:** live candlestick + signal overlays in browser; Streamlit decommissioned

### Phase 6 — D09 (~2 weeks)
- LSTM training pipeline on combined F+T feature set (D03 + D04 features, both lagged
  to avoid look-ahead — see D09's Known Risks)
- CPCV validation before model promotion (uses D08)
- Staging shadow mode (2 weeks, logs predictions without trading) before prod promotion
- Rollback procedure for underperforming models, with a 24-hour cooldown between
  rollbacks to prevent a rollback storm in a regime where nothing performs well
- Writes promoted model as a `ModelArtifact` to the registry; D05 picks it up on next
  poll (default every 5 minutes), never mid-fusion-cycle
- **Milestone:** model in staging, evaluated against weighted combiner baseline

### Phase 7 — D11 + Redis Bus (~2 weeks)
- D11: division health checks, bus latency metrics, data freshness alerts (session-hours
  aware, to avoid false positives every weekend), model drift monitoring
- Swap InProcessBus → RedisBus (one config line change; no code changes in other divisions)
- **Milestone:** any division failure triggers a Telegram alert via D07; multi-process
  deployment works (D08/D09 can now run on separate hosts from the live loop)

---

## Cross-Cutting Concerns

### Clock
All current-time access must go through `from src.core.clock import now`.
`datetime.utcnow()`, `datetime.now()`, and `time.time()` are **banned** outside
`src/core/clock.py`. In live mode the clock returns UTC now. In replay mode it returns
the current bar's timestamp. Only D08-BACKTEST calls the `ControllableClock` control
methods (`set_replay_time`, `advance`, `reset_to_live`). When D10's replay page drives
a session, it calls D08's API, which calls the clock — the UI never touches the clock
directly. Within D08's feed loop, `advance()` must be called and awaited with no
intervening `await` before `bus.publish()` — reversing this order is the single most
damaging bug class for a backtest, since it opens the door to look-ahead bias.

### Signal Bus
Two implementations in D01, selected via `core.bus_backend` config:
- `memory` → InProcessBus (asyncio.Queue, default for dev and single-process)
- `redis` → RedisBus (Redis pub/sub, for multi-process production)
All divisions use only the `Bus` protocol interface — never instantiate a bus directly.
The bus instance is injected at startup from the composition root.

Topics are a flat `BusChannel` enum (`OHLCV_BAR`, `ECONOMIC_EVENT`,
`FUNDAMENTAL_SIGNAL`, `TECHNICAL_SIGNAL`, `TRADE_SIGNAL`, `ORDER_EVENT`,
`PORTFOLIO_UPDATE`, `SYSTEM_HEALTH`) rather than per-instrument topic strings —
every subscriber gets all instruments on a channel and filters by the `instrument`
field on the payload. See CONTRACTS.md for the canonical list; don't invent new
channels without adding them there first.

### Model Artifact Handoff (D09 → D05)
D09 never runs live and D05 never imports D09. The registry file
(`data/models/registry.json`, written by D09's `registry.py`) is the only contract
between them: D09 writes a `ModelArtifact` record on promotion, D05 polls the file
(default every 5 minutes) and reloads inference weights only when `model_id` changes,
never mid-fusion-cycle. See CONTRACTS.md's Model Registry Artifact section for the schema.

### Safety Gates
`execution.mode` (`paper` | `live`) is a hard config flag in D06's `mode_gate.py`.
Switching to `live` requires two factors: `execution_mode: live` in YAML, **and**
`LIVE_TRADING_CONFIRMED=YES` set manually in the shell each session — this variable
must never live in `.env`, specifically so a live-trading session can't start silently
from a checked-in config. Live mode is further restricted to `env: prod`.

### Secrets
No secrets in YAML config files. Required `.env` / shell variables, by the division
that consumes them:
- D02: `NEWSAPI_KEY`, `FRED_API_KEY`
- D03: `OPENROUTER_API_KEY` (optional — signals still work without narrative),
  `OPENROUTER_DAILY_BUDGET`
- D06: `OANDA_API_KEY`, `OANDA_ACCOUNT_ID` (live mode only),
  `LIVE_TRADING_CONFIRMED` (shell only, never `.env` — see Safety Gates above)
- D07: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (comma-separated list ok for multiple destinations; secrets), `ALLOWED_TELEGRAM_USER_IDS`
See `.env.example` (comprehensive and grouped by division). Each division MD's "Environment Variables Required" section is the source of truth. Update both when adding new integrations (e.g. MT5, IBKR).

### Logging
Structured JSON logging everywhere using Python `structlog` or `logging` with a JSON
formatter. Every log record includes: `division`, `signal_id` (correlation), `instrument`,
`timestamp`. `signal_id` flows through all log entries for a signal's full lifecycle
(fetch → signal → trade → fill). D11's `log_aggregator.py` indexes by `signal_id` so a
single trade's full history can be reconstructed across every division that touched it.

### Instrument Config
Each instrument defined in `config/instruments.yaml`: **`enabled`** flag (D02 scheduler /
refresh / chart UI), pip size, lot size, session hours, optional `daily_break` (gold),
active timeframes, fundamental/technical weight split, max position size, news halt
window, and per-event-type signal decay hours. All divisions load instrument config via
`load_instruments() → InstrumentConfig`. The `Instrument` enum in `contracts.py` is
identity only (what the platform can speak about). Env YAML (`dev.yaml`) holds deployment
settings (`data.pipeline`, model, risk) — not per-pair trading rules. See CONTRACTS.md.

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
  ops.yaml        ← D11 alert thresholds
data/
  raw/            ← OHLCV Parquet files
  news/           ← news article store
  models/         ← model registry (written by D09, read by D05; see registry.json)
  reports/        ← D08 backtest/replay reports
  state/          ← D06 position persistence (positions.json)
logs/
  audit_{date}.jsonl   ← D06 audit log, 90-day retention
  ops_alerts.jsonl     ← D11 fallback alert path when the bus itself is down
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
- **Coverage gates are set per division**, not a single flat number — see each
  division MD's Testing Strategy section. As a rough guide: D01-CORE and
  D06-EXECUTION (critical path — contracts/bus and real-money execution) carry the
  highest bar at 80%; most analytical and offline divisions sit at 55–70%; D10's
  backend targets 50% with Playwright E2E covering the frontend separately.
- **Env vars:** `PYTHONPATH=src`, `CONFIG_DIR=$(pwd)/config` in all test runs
- **No secrets** in YAML, code, or committed files
- **No `datetime.now()`** outside `src/core/clock.py` — enforced by ruff custom rule or pre-commit hook
- **Signal IDs** on every signal object, generated via `src.core.ids.new_signal_id()` —
  never inline `str(uuid.uuid4())`. Log them on every operation touching that signal.
- **Fail loud:** data fetch failures raise exceptions and surface to D11; never silently
  return empty data

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
