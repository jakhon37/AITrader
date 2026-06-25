# AITrader Project Status & Roadmap

*Last updated: 2026-06-25*

## Executive Summary

All core tiers through **Tier 5 foundations** are implemented and covered by automated tests in Docker. The platform runs a full live spine in the Web UI: data → technical → fundamental → decision → execution → Telegram notifier.

| Tier | Focus | Status |
|------|--------|--------|
| **Tier 1** | D02 data stabilization | ✅ Complete + 74 tests pass |
| **Tier 2** | Live signal spine (TA → Decision → Trade) | ✅ Complete |
| **Tier 3** | D03 Fundamental + D07 Telegram | ✅ Complete |
| **Tier 4** | Full paper loop (fusion, news halt, audit) | ✅ Complete |
| **Tier 5** | D09 registry read + D11 ops pipeline health | ✅ Foundations complete |

**Next operational milestone:** 2-week paper trading soak (human validation, not code).

---

## Status by Division

| Division | Name | Status | Notes |
|----------|------|--------|-------|
| **D01** | CORE | ✅ Complete | contracts, bus, clock, config |
| **D02** | DATA | ✅ Complete | Dukascopy, scheduler, calendar SQLite, gap-fill |
| **D03** | FUNDAMENTAL | ✅ Complete | Agent + news/calendar fetchers in `main.py`; pre-release briefings |
| **D04** | TECHNICAL | ✅ Complete | Live `TechnicalEngine` on OHLCV_BAR |
| **D05** | DECISION | ✅ Complete | F+T fusion, registry `model_version`, neutral dedupe |
| **D06** | EXECUTION | ✅ Complete | Paper engine, news halt circuit breaker |
| **D07** | NOTIFIER | ✅ Complete | Telegram with blocked-chat skip; DM delivery |
| **D08** | BACKTEST | ✅ Complete | Replay + strategy loop with FundamentalAgent |
| **D09** | TRAINER | 🔶 Registry | 22 model versions; prod promotion manual |
| **D10** | WEBUI | ✅ Complete | Terminal, Fusion+News panels, calendar API |
| **D11** | OPS | 🔶 Partial | `/api/health` + `/api/health/pipeline` |

---

## Live architecture

```
Dukascopy → DataStore → Chart API
                ↑
         DataScheduler → OHLCV_BAR ─┬→ WebSocket → Chart
                                   ├→ TechnicalEngine → TECHNICAL_SIGNAL
                                   │
         NewsFetcher / CalendarFetcher
                    ↓
              FundamentalAgent → FUNDAMENTAL_SIGNAL
                                   ↓
                            DecisionEngine → TRADE_SIGNAL
                                   ↓
                            ExecutionEngine (paper) + Notifier (Telegram)
```

---

## Tier deliverables (validated)

### Tier 1 — D02 stabilization ✅
- Config single source (`instruments.yaml`)
- Focus scheduler, gap-fill, live-status fix
- Tests: `test_data_scheduler`, `test_data_sources`, `test_data_store`, `test_data_pipeline`

### Tier 2 — Live signal spine ✅
- `TechnicalEngine` + `DecisionEngine` in `main.py`
- WebSocket + Fusion / Signal Log
- Tests: `test_live_signal_spine.py`

### Tier 3 — Fundamental + Telegram ✅
- `FundamentalAgent`, `NewsFetcher`, `CalendarFetcher`, `NotifierService` in lifespan
- News Sentinel: scheduled + live feed; calendar briefings via OpenRouter
- Calendar API: `GET /api/data/calendar/upcoming`
- Tests: `test_fundamental.py`, `test_notifier.py`, `test_signal_spine_e2e.py`

### Tier 4 — Paper loop ✅
- Fusion weights from `instruments.yaml`
- High-impact `ECONOMIC_EVENT` → news halt → execution blocked
- Fusion panel shows F + T bias and weights
- Tests: `test_signal_spine_e2e.py`, `test_decision.py`, `test_execution*.py`

### Tier 5 — Registry + OPS ✅ (foundations)
- `resolve_active_model_version()` → `TradeSignal.model_version`
- `GET /api/health/pipeline` — component running status
- Tests: `test_decision_registry.py`, `test_api.py::test_pipeline_health_endpoint`

---

## Known operational notes

| Item | Action |
|------|--------|
| Telegram group chat 400 | Add bot as admin with Post Messages, or use DM-only `TELEGRAM_CHAT_ID` |
| Calendar empty | Forex Factory scrape may return 0 events; wait for hourly poll |
| Backend code changes | `docker restart aitrader-webui-backend` (no hot-reload) |
| 2-week paper soak | `./scripts/start_paper.sh` — not yet run to completion |

---

## Run / verify

```bash
# Full test gate (Docker)
./docker/docker_dev_test.sh

# Tier-specific
./docker/docker_dev_test.sh tests/integration/test_signal_spine_e2e.py -v
./docker/docker_dev_test.sh tests/unit/test_live_signal_spine.py -v

# Web UI
./scripts/start_webui.sh

# Pipeline health
curl -s http://localhost:8000/api/health/pipeline | python3 -m json.tool
```

---

## Reference docs

- [MASTER.md](MASTER.md) — division map
- [D03-FUNDAMENTAL.md](D03-FUNDAMENTAL.md) — sentiment backends
- [D10-WEBUI.md](D10-WEBUI.md) — terminal spec