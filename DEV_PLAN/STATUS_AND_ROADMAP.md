# AITrader Project Status & Roadmap

*Last updated: 2026-06-25*

## Executive Summary

AITrader follows the modular division plan in `DEV_PLAN/MASTER.md`. Core infrastructure, backtest/replay, and the Web UI terminal are operational. The **live chart + Dukascopy data pipeline** (D02) is stabilized. The **live signal spine** (OHLCV_BAR → TechnicalEngine → DecisionEngine → Fusion panel + Signal Log) is wired in `main.py`.

| Milestone | Status |
|-----------|--------|
| Phase 0 — Contracts | ✅ Done |
| Phase 1 — D01 + D02 | ✅ Done (D02 polish in progress — see Tier 1 below) |
| Phase 2 — D04 + D08 | ✅ Done |
| Phase 3 — D03 + D07 | 🔶 Code exists; not live in WebUI |
| Phase 4 — D05 + D06 | 🔶 Code + unit tests; not end-to-end in terminal |
| Phase 5 — D10 Web UI | ✅ Charts/data/replay + live fusion panels |
| Phase 6+ — D09 ML, D11 OPS, live broker | 🔴 Future |

---

## Status by Division

| Division | Name | Status | Notes |
|----------|------|--------|-------|
| **D01** | CORE | ✅ Complete | `contracts.py`, bus, clock, `instruments.yaml` loader, session helpers |
| **D02** | DATA | 🔶 **Stabilizing** | Dukascopy live poll, auto-refresh, 4 instruments, adaptive poll, gap-fill. Tier 1 polish active. |
| **D03** | FUNDAMENTAL | 🔶 Partial | `FundamentalAgent` + tests; not started in `main.py` lifespan |
| **D04** | TECHNICAL | ✅ Complete | `TechnicalEngine` subscribed to live `OHLCV_BAR` in WebUI |
| **D05** | DECISION | 🔶 Partial | `DecisionEngine` live; publishes `TradeSignal` (fundamental=None) |
| **D06** | EXECUTION | 🔶 Partial | `ExecutionEngine` runs in WebUI (paper); receives live trade signals |
| **D07** | NOTIFIER | 🔶 Partial | Telegram modules + tests; service not started |
| **D08** | BACKTEST | ✅ Complete | Replay, CPCV, manual mode, HTML reports |
| **D09** | TRAINER | 🔶 Legacy | Model registry (22 versions); not wired to live fusion |
| **D10** | WEBUI | ✅ Data layer | Terminal, 1m–1d charts, TZ selector, live status, config API |
| **D11** | OPS | 🔴 Minimal | `/api/health` only |

---

## Config architecture (aligned 2026-06-25)

| Layer | Source | Purpose |
|-------|--------|---------|
| Identity | `src/core/contracts.py` → `Instrument` enum | Valid symbols |
| Per-instrument | `config/instruments.yaml` | `enabled`, pip, session, weights, `daily_break` |
| Deployment | `config/dev.yaml` | Pipeline cadence, model, risk (no per-pair trading rules) |

---

## Hardware Note (Development)
Primary dev machine: 2020 Intel MacBook Pro 16GB RAM.
- FinBERT is supported but will default to disabled or mock mode.
- OpenRouter is the practical path for narratives and optional sentiment on this hardware.
- Full local FinBERT is intended for GPU-equipped machines and production.

See D03-FUNDAMENTAL.md for pluggable backend strategy.

## D02 live data — what works today

- All four instruments enabled: EURUSD, GBPUSD, USDJPY, XAUUSD
- Live scheduler bootstraps H1 background polls; chart focus switches to M1–1d
- Adaptive poll intervals (slower mid-candle for H1/1d)
- Auto-refresh: hourly M1 tail + resample; daily 4h/1d
- Gap-fill: non-blocking for intraday when `auto_refresh` on
- Chart session filter: FX weekend + gold daily break
- Frontend: instruments from `GET /api/data/instruments`, timezone selector

---

## Tier 1 — D02 stabilization (current sprint)

**Goal:** Reliable intraday charts under Docker without Dukascopy lock contention.

| Task | Status |
|------|--------|
| Config single source (`instruments.yaml` `enabled`) | ✅ Done |
| Focus scheduler before gap-fill | ✅ Done |
| Non-blocking intraday gap-fill | ✅ Done |
| Live status false "Feed offline" fix | ✅ Done |
| Prune `active_pairs` on timeframe switch | ✅ Done |
| Defer startup refresh during intraday focus | ✅ Done |
| Full test gate in Docker | ⏳ Run `./docker/docker_dev_test.sh` |

---

## Live Web UI architecture (today)

```
Dukascopy → DataStore → /api/data/ohlcv → Chart
                ↑
         DataScheduler → OHLCV_BAR ─┬→ WebSocket → Chart
                                   ├→ TechnicalEngine → TECHNICAL_SIGNAL
                                   │         ↓
                                   │   DecisionEngine → TRADE_SIGNAL
                                   │         ↓
                                   └→ ExecutionEngine (paper) + WS → Fusion / Signal Log
```

`src/api/main.py` starts: Bus, DataScheduler, TechnicalEngine, DecisionEngine, ExecutionEngine, DataRefreshWorker.  
Does **not** start: FundamentalAgent, Telegram notifier.

**Note:** Technical fusion runs on each instrument's **primary timeframe** close (typically 1h), not on every chart TF switch. Replay pauses the live spine via `signal_pipeline.py`.

---

## What is next (priority order)

### Tier 2 — Live signal spine ✅ Done (2026-06-25)

- `TechnicalEngine` + `DecisionEngine` in `main.py` lifespan
- `GET /api/signals/latest?instrument=` for bootstrap
- Fusion panel + Signal Log via WebSocket (`technical_signal`, `trade_signal`)
- Replay pause/resume in `replay.py`
- Tests: `tests/unit/test_live_signal_spine.py`

### Tier 3 — Phase 3 (D03 + D07, ~2–3 weeks) — **Revised Plan (2026-06-25)**

**Key Decisions** (see `D03-FUNDAMENTAL.md` for full details):
- Sentiment backend is now **pluggable** (`finbert` / `mock` / `openrouter`).
- Development hardware (Intel 16GB Mac) will primarily use mock + OpenRouter LLM path.
- GPU / production deployments will use local FinBERT.
- Explicitly **no** CrewAI or heavy LLM agent frameworks.
- Full wiring of ingestion + processing into live + replay.

#### Priorities
- Make sentiment scoring **pluggable**:
  - `finbert` (local, high-quality, preferred on GPU)
  - `mock` (fast dev)
  - `openrouter` (LLM API fallback using structured output)
- On current dev hardware (Intel 16GB Mac): default to `mock` + OpenRouter.
- On GPU / production devices: enable real FinBERT.
- **Do not** use CrewAI / heavy agent frameworks (too heavy, non-deterministic, costly for free-tier OpenRouter, conflicts with replay determinism and explicit bus architecture).
- Wire `FundamentalAgent` (revised) into:
  - Live WebUI (`src/api/main.py`)
  - Modern replay (`src/backtest/replay/strategy/`)
- Start supporting ingestion services: `NewsFetcher` + `CalendarFetcher`
- Improve:
  - Push-preferring triggers (calendar events + optional news events)
  - Caching for sentiment scores
  - Time-weighted aggregation + calendar correlation
  - Macro regime quality
  - Structured LLM usage on OpenRouter (narrative + optional sentiment)
- Ensure replay can feed historical data deterministically
- Add basic integration test that `FUNDAMENTAL_SIGNAL` flows through the spine

#### Deliverables
- Configurable `fundamental.sentiment_backend`
- FundamentalAgent + components updated per revised design
- News + Calendar fetchers started in main lifespan
- Replay support for historical fundamentals
- Updated UI / API surfaces can now receive real fundamental signals

See full revised plan in [D03-FUNDAMENTAL.md](D03-FUNDAMENTAL.md).

### Tier 4 — Phase 4 full paper loop (~2 weeks)

- D05 fusion v1 with `instruments.yaml` weights
- D06 economic calendar circuit breaker
- 2-week paper trading with audit traceability

### Tier 5 — Later

- D09 model promotion → D05 registry read
- D11 ops monitoring
- Live broker (after paper validation)

---

## Run / verify

```bash
# Web UI
bash scripts/start_webui.sh

# Live status
curl -s http://localhost:8000/api/data/live-status | python3 -m json.tool

# Tests (Docker)
./docker/docker_dev_test.sh
```

---

## Reference docs

- [MASTER.md](MASTER.md) — division map and build phases
- [CONTRACTS.md](CONTRACTS.md) — shared schemas
- [D02-DATA.md](D02-DATA.md) — data pipeline spec