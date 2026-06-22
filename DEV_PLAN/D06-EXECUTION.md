# D06 — EXECUTION

## Purpose
Order management, broker bridge, and risk enforcement. Subscribes to TradeSignal,
runs risk checks, submits orders to the active broker, tracks positions,
publishes order events and portfolio state. Where real money is committed.

Does NOT: produce signals, fetch data, train models, or send notifications (D07).
Receives one signal type, enforces risk rules, manages orders.

---

## Dependencies
- D01-CORE: contracts, bus, clock, config, logging
- D05-DECISION: subscribes to BusChannel.TRADE_SIGNAL (bus only)
- D02-DATA: subscribes to BusChannel.ECONOMIC_EVENT (news halt); BusChannel.OHLCV_BAR (mark-to-market)

---

## Emits
| Channel | Type | When |
|---|---|---|
| BusChannel.ORDER_EVENT | OrderEvent | Each order lifecycle transition |
| BusChannel.PORTFOLIO_UPDATE | PortfolioState | After every OrderEvent + on price update |

---

## Internal Module Structure

```
src/execution/
  __init__.py
  engine.py           <- existing; refactor to consume TradeSignal; add mode_gate
  risk_manager.py     <- existing; extend with new checks
  circuit_breaker.py  <- existing; add economic calendar trigger
  position_manager.py <- existing; add PortfolioState bus publishing
  audit_log.py        <- existing; add signal_id correlation
  mode_gate.py        <- NEW: hard paper/live mode switch
  brokers/
    base.py           <- Broker protocol
    sim.py            <- existing SimBroker; refactor for typed Order/OrderEvent
    oanda.py          <- future stub (raises NotImplementedError)
    mt5.py            <- future stub
```

### engine.py
Three bus subscriptions:
1. BusChannel.TRADE_SIGNAL -> main trading trigger
2. BusChannel.ECONOMIC_EVENT -> news halt activation/deactivation
3. BusChannel.OHLCV_BAR -> mark-to-market + SL/TP monitoring

On TradeSignal:
1. mode_gate.check()
2. circuit_breaker.allow(instrument)
3. risk_manager.validate(signal, portfolio)
4. If all pass: build Order; broker.submit(order)
5. Publish OrderEvent("created"); on fill callback: OrderEvent("filled")
6. Publish PortfolioState

### risk_manager.py
Pre-trade checks:
- Max position size vs instrument_config.max_position_lots
- Max concurrent open positions (default 3 globally)
- Free margin > order_margin * 1.5 (safety factor)
- Correlation check: reduce size if correlated instrument already open
- Min confidence: signal.confidence >= risk.min_confidence (default 0.4)
- Signal age: TradeSignal.valid_until > clock.now()
- Session hours: instrument active market hours only
Returns RiskDecision(approved, reason, adjusted_size).

### circuit_breaker.py
Three trigger types:

Trigger 1 — Daily loss limit:
realized_pnl_today < -(max_daily_loss_pct * starting_balance) -> halt all trading

Trigger 2 — Consecutive loss streak:
consecutive_losses >= max_consecutive_losses (default 3) -> halt 2 hours then reset

Trigger 3 — Economic calendar halt (NEW):
On EconomicEvent with impact=HIGH:
- Activate halt news_halt_minutes before scheduled time for affected instruments
- Deactivate news_halt_minutes after scheduled time
- Only affects instruments in event.affected_pairs; others continue

### mode_gate.py (NEW)
Hard enforcement of paper vs live mode.

```python
def check(self) -> None:
    if config.execution_mode == LIVE:
        if os.getenv("LIVE_TRADING_CONFIRMED") != "YES":
            raise ExecutionError(
                "Live mode requires LIVE_TRADING_CONFIRMED=YES in shell env. "
                "Cannot be in .env — must be set explicitly."
            )
        if config.env != "prod":
            raise ExecutionError("Live trading only allowed in prod environment.")
```

Two-factor for live: (1) execution_mode: live in YAML + (2) LIVE_TRADING_CONFIRMED=YES in shell.
The env var must NOT be in .env — it must be set manually in the shell each session.

### position_manager.py
Now publishes PortfolioState to bus after every position change.
On each OHLCVBar: mark-to-market all open positions; check SL/TP hit; publish updated state.
Persists position state to data/state/positions.json after every change (crash recovery).
On startup: loads positions.json if it exists (critical for live trading continuity).

### audit_log.py
All records include signal_id for end-to-end correlation.
JSON lines to rolling file logs/audit_{date}.jsonl.
Retention: 90 days; compress older files; D11 monitors disk usage.

---

## Existing Code to Migrate

| Existing | Action |
|---|---|
| src/execution/engine.py | Major refactor: consume TradeSignal; add mode_gate; add OHLCV subscription |
| src/execution/risk_manager.py | Add: correlation, min-confidence, signal-age checks |
| src/execution/circuit_breaker.py | Add: economic calendar trigger type |
| src/execution/position_manager.py | Add: PortfolioState publishing; position persistence |
| src/execution/audit_log.py | Add: signal_id on all records |
| src/execution/brokers/sim.py | Refactor: typed Order/OrderEvent; SL/TP via engine |

---

## Environment Variables Required
```
LIVE_TRADING_CONFIRMED  # must be "YES" to enable live; set in shell, NOT .env
OANDA_API_KEY           # live mode with OANDA only
OANDA_ACCOUNT_ID        # live mode with OANDA only
```

---

## Testing Strategy
Coverage target: 80% (real money risk path; highest priority).

Unit:
- risk_manager.py: each check independently; size cap; margin check; correlation; min confidence
- circuit_breaker.py: daily loss trigger; streak trigger; calendar halt by instrument;
  boundary: 1s before halt_start -> allowed; at halt_start -> blocked
- mode_gate.py: paper -> always passes; live without env var -> raises; live with env + prod -> passes
- sim.py: market order fills with slippage within bounds; SL trigger; commission calc

Integration:
- Full trade lifecycle: TradeSignal -> risk pass -> OrderEvent(created) -> fill -> PortfolioUpdate
- Risk rejection: oversized signal -> OrderEvent(rejected); portfolio unchanged
- News halt: HIGH EconomicEvent for EURUSD -> all EURUSD signals blocked; other instruments unaffected
- NEUTRAL TradeSignal -> open position for that instrument is closed

---

## Implementation Phases

### Phase 4 (MASTER Phase 4)
1. Write mode_gate.py
2. Write brokers/base.py (Broker protocol)
3. Refactor brokers/sim.py
4. Extend risk_manager.py
5. Add calendar trigger to circuit_breaker.py
6. Add PortfolioState publishing + position persistence to position_manager.py
7. Add signal_id to audit_log.py
8. Refactor engine.py — full pipeline with all subscriptions
9. Integration tests
10. Milestone: paper trading loop running; trades logged with signal_id

### Phase 5+ (live broker)
11. Implement brokers/oanda.py against OANDA v20 REST
12. Live integration tests on OANDA practice account
13. ModeGate live path full verification

---

## Known Risks

**SL/TP slippage in simulation.** SimBroker fills at exact price. Add sl_slippage_pips
for more realistic gap simulation around news events.

**Position state loss on restart.** positions.json persistence (see position_manager.py)
is mandatory before any live trading. Test: kill process with open position; restart;
verify position correctly recovered.

**Correlated positions.** Static instrument-group correlation is a simplification.
Correlation changes dynamically. Plan dynamic correlation matrix from recent prices for v2.

**Thread safety in position_manager.** asyncio.Lock around all position state reads/writes.
