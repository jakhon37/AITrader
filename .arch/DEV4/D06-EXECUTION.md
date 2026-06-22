# D06 — EXECUTION

## 1. Purpose & boundaries
Order lifecycle management: submit → fill → track → close. Owns `SimBroker` (paper
trading, also reused by D08's backtest/replay) and the live broker bridge. Owns the risk
manager, circuit breaker (including the economic-calendar halt trigger), audit log, and
the paper/live mode gate. **Does not generate trade decisions** (D05 does) and **does not
backtest** (D08 reuses this division's SimBroker, but the backtest orchestration lives there).
This is where real money touches the system — held to the highest review bar in the codebase.

## 2. Dependencies
D01. Subscribes to `signals.trade.*` from D05 via the bus. Reads D02's economic calendar
store directly for the circuit breaker's news-window halt trigger (this is a direct data
read, not a bus subscription — calendar events are infrequent and need to be queried
ahead of time, e.g. "is there a high-importance event in the next 30 minutes").

## 3. Emits / exposes
Bus topic:
- `execution.fill.{instrument}` — fired on every fill, consumed by D07 (notifier) and readable by D11 (ops).

Direct read API:
- `PortfolioState` (per CONTRACTS.md), read by D10 for the portfolio panel.

## 4. Internal module structure
```
src/execution/
  __init__.py
  engine.py              # order executor; refactored to consume TradeSignal from the bus
  brokers/
    base.py              # Broker abstract protocol
    sim.py               # simulated paper-trading broker (reused by D08 backtest/replay)
    oanda.py             # live OANDA REST API client (future)
  position_manager.py    # tracks active trades and sizes
  risk_manager.py        # validates trading limits (daily drawdowns, position limits)
  circuit_breaker.py     # halts trading on limit violations or economic calendar news windows
  audit_log.py           # production-grade structured event logging
  mode_gate.py           # safety mode gate; requires explicit env var + startup confirmation
```

## 5. Existing code to migrate
`engine.py`, `brokers/sim.py`, `position_manager.py`, `risk_manager.py`,
`circuit_breaker.py`, `audit_log.py` all exist and stay largely as-is. The required
changes are: (1) `engine.py` consumes `TradeSignal` from the bus instead of whatever
ad-hoc input it currently takes, (2) `circuit_breaker.py` gets a new trigger type for
calendar events, (3) `mode_gate.py` is new.

## 6. Testing strategy
**Coverage target: 80%** (critical path, same tier as D01-CORE).
- Circuit breaker: drawdown trigger, loss-streak trigger, and the new news-window halt
  trigger each tested independently and in combination
- Paper/live gate: must require explicit env var + confirmation; test that a bare YAML
  edit alone cannot switch to live mode
- SimBroker: fill price and slippage model tests against known input scenarios
- Race condition test: circuit breaker halt firing while an order is in-flight — confirm
  no order is submitted after halt, and any in-flight order resolves safely

## 7. Implementation phases (internal)
1. Refactor `engine.py` to consume `TradeSignal` — Phase 4, week 1
2. Economic calendar circuit breaker trigger (direct query D02) — Phase 4, week 1–2
3. Paper/live hard gate — Phase 4, week 2

## 8. Known risks & gotchas
- **Economic Calendar Query vs Subscription:** Relying on transient event broadcasts is a logical failure. If the execution service restarts, it misses the news event publication. Implementing a **proactive direct query** against `D02`'s database at regular intervals ensures circuit breaker safety.
- **Slippage Model Accuracy:** SimBroker's slippage settings determine backtest reliability. Update slippage formulas against actual paper-trading fills.
- **Paper/Live Gate Security:** Live mode activation must never rely solely on a YAML config. Force an environment variable check (e.g. `LIVE_TRADING_CONFIRMED=1`) plus a terminal validation prompt at boot.
