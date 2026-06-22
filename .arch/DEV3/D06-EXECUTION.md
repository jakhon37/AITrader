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
Bus topic: `execution.fill.{instrument}` — fired on every fill, consumed by D07 (notifier)
and readable by D11 (ops).

Direct read API: `PortfolioState` (per CONTRACTS.md), read by D10 for the portfolio panel.

## 4. Internal module structure
```
src/execution/
  engine.py              # existing — refactor to consume typed TradeSignal from the bus
  brokers/
    sim.py                 # existing SimBroker — reused by D08 backtest/replay unchanged
    oanda.py                 # NEW, future — live broker bridge, built but gated off by default
  position_manager.py        # existing — tracks active trades and sizes
  risk_manager.py              # existing — daily drawdown, position limits
  circuit_breaker.py             # existing — extend with economic-calendar halt trigger
  audit_log.py                     # existing — structured event logging
  mode_gate.py                       # NEW — hard paper/live switch with confirmation gate
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
2. Economic calendar circuit breaker trigger — Phase 4, week 1–2
3. Paper/live hard gate — Phase 4, week 2

## 8. Known risks & gotchas
- **Live broker API differences** (OANDA REST vs MT5 bridge) — design `brokers/` as a
  protocol/interface from the start so adding a second live broker doesn't touch
  `engine.py`.
- **Slippage model accuracy** — SimBroker's slippage assumptions directly determine how
  trustworthy backtest results are; revisit this against live paper-trading fill data
  once available, don't treat it as fixed.
- **Race condition between circuit breaker halt and in-flight orders** — the highest-risk
  bug class in this division; needs explicit test coverage, not just code review.
- **News-window halt false positives** — low-importance calendar events shouldn't trigger
  a full halt; tune the importance threshold deliberately and make it configurable per instrument.
