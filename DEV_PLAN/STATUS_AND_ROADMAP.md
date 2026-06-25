# AITrader Project Status & Roadmap

*Last updated: 2026-06-25*

## Executive Summary

AITrader follows the modular division plan in `DEV_PLAN/MASTER.md`. Core infrastructure, backtest/replay, and the Web UI terminal are operational. The **live chart + Dukascopy data pipeline** is the current focus area (D02 stabilization). The **live signal pipeline** (Technical → Decision → Execution on the bus) is implemented as modules but **not yet wired** into the Web UI process.

| Milestone | Status |
|-----------|--------|
| Phase 0 — Contracts | ✅ Done |
| Phase 1 — D01 + D02 | ✅ Done (D02 polish in progress — see Tier 1 below) |
| Phase 2 — D04 + D08 | ✅ Done |
| Phase 3 — D03 + D07 | 🔶 Code exists; not live in WebUI |
| Phase 4 — D05 + D06 | 🔶 Code + unit tests; not end-to-end in terminal |
| Phase 5 — D10 Web UI | ✅ Charts/data/replay; signal panels await bus wiring |
| Phase 6+ — D09 ML, D11 OPS, live broker | 🔴 Future |

---

## Status by Division

| Division | Name | Status | Notes |
|----------|------|--------|-------|
| **D01** | CORE | ✅ Complete | `contracts.py`, bus, clock, `instruments.yaml` loader, session helpers |
| **D02** | DATA | 🔶 **Stabilizing** | Dukascopy live poll, auto-refresh, 4 instruments, adaptive poll, gap-fill. Tier 1 polish active. |
| **D03** | FUNDAMENTAL | 🔶 Partial | `FundamentalAgent` + tests; not started in `main.py` lifespan |
| **D04** | TECHNICAL | ✅ Complete | `TechnicalEngine`; not subscribed to live bus in WebUI |
| **D05** | DECISION | 🔶 Partial | `DecisionEngine` + tests; no live `TradeSignal` publisher |
| **D06** | EXECUTION | 🔶 Partial | `ExecutionEngine` runs in WebUI (paper); awaits live trade signals |
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
         DataScheduler → OHLCV_BAR → WebSocket → Chart

NOT wired yet:
  OHLCV_BAR → TechnicalEngine → DecisionEngine → TradeSignal → Fusion panel
```

`src/api/main.py` starts: Bus, DataScheduler, ExecutionEngine, DataRefreshWorker.  
Does **not** start: TechnicalEngine, FundamentalAgent, DecisionEngine.

---

## What is next (priority order)

### Tier 2 — Live signal spine (~1 week)

Wire in `main.py`:

1. `TechnicalEngine` subscribes to `OHLCV_BAR` → `TechnicalSignal`
2. `DecisionEngine` → `TradeSignal` (fundamental=None OK initially)
3. Fusion panel + Signal Log populate via existing WebSocket bridge

**Milestone:** Terminal shows live technical fusion on chart instrument.

### Tier 3 — Phase 3 (D03 + D07, ~2–3 weeks)

- Wire `FundamentalAgent` into live + replay
- Telegram notifier service
- Replay bus gets historical fundamental signals

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