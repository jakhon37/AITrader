# D08 — BACKTEST

## Purpose
Offline simulation engine with three modes: automated backtesting (CPCV + walk-forward),
strategy replay (watch mode), and manual replay (trader training). Runs against historical
data using the same pipeline as live trading, controlled by VirtualClock.
The only division that calls clock control methods.

Does NOT: run in the same process as live trading; fetch live data; train models (D09);
push signals to the production bus during replay.

---

## Dependencies
- D01-CORE: contracts, bus, ControllableClock (exclusive caller of control methods), config, logging
- D02-DATA: DataStore.get_ohlcv(), get_news(), get_economic_events() (historical reads only)
- D03-FUNDAMENTAL: imports FundamentalAgent directly (local instance, not via bus).
  **Phased: not available until Phase 3.** D08's own build starts in Phase 2, before
  D03 exists — see Implementation Phases below for what "replay" means before vs. after
  this dependency comes online.
- D04-TECHNICAL: imports TechnicalEngine directly (local instance, not via bus)
- D05-DECISION: imports DecisionEngine directly (local instance) — note D05 itself
  expects both fundamental and technical signal input (gracefully handling fundamental=None
  per its expiry.py design), so omitting D03 from the isolated bus doesn't break D05,
  it just means D05 always falls back to technical-only fusion until D03 is wired in.
- D06-EXECUTION: imports SimBroker + ExecutionEngine directly (never live broker)

D08 creates private instances of D03/D04/D05/D06 wired to an ISOLATED in-process bus.
Replay signals never appear on the production bus. This is enforced by design, not convention.

---

## Emits
Nothing onto the production bus. Results written to disk as report files.
ReplayFrame events go to the D10 WebSocket endpoint (not the bus).

---

## Internal Module Structure

```
src/backtest/
  __init__.py
  runner.py          <- CLI entry point; mode selector; isolated bus setup
  feed.py            <- bar-by-bar data feeder; advances ReplayClock; streams Parquet
  engine.py          <- existing AutoBacktestEngine; refactored to use feed.py
  cpcv.py            <- existing CPCV; unchanged
  walk_forward.py    <- existing walk-forward; unchanged
  replay.py          <- NEW: StrategyReplaySession + ManualReplaySession
  session_state.py   <- NEW: thread-safe session state for UI consumption
  scorer.py          <- NEW: manual replay performance scoring
  reporter.py        <- NEW: unified report generator (JSON + HTML + console)
  websocket.py       <- NEW: ReplayFrame emitter for D10 browser UI
```

### runner.py
CLI: python -m src.backtest.runner --mode auto|replay|manual --instrument EURUSD
     --start 2023-01-01 --end 2023-12-31 --timeframe 1h

Also callable programmatically from D10 replay API endpoint.

Setup sequence:
1. Instantiate ReplayClock
2. Create isolated InProcessBus (replay bus)
3. Instantiate D04 TechnicalEngine, D05 DecisionEngine, D06 SimBroker + ExecutionEngine,
   and (once Phase 3 lands) D03 FundamentalAgent fed from D02's historical news/calendar
   store instead of live polling — all wired to the REPLAY bus and ReplayClock (not
   production bus/clock). Before Phase 3, step 3 simply omits D03; D05 already handles
   a missing fundamental signal gracefully, so this isn't a special case to code around.
4. Create DataFeed for selected instrument, TF range, date range
5. Assert broker is SimBroker (hard runtime check — never live in replay)
6. Delegate to the appropriate session class

### feed.py
Reads historical bars from D02 DataStore. Controls ReplayClock on each bar advance.
Streams Parquet via pyarrow.dataset.Scanner — never loads full history into memory.

```python
class DataFeed:
    async def run(self, speed: float = 0.0) -> AsyncIterator[OHLCVBar]:
        # speed=0.0: step-by-step (manual mode / fast auto backtest)
        # speed=1.0: real-time wall-clock
        # speed=100.0: fast-forward (100x real time)
        # Emits bars in chronological order across all active timeframes.
        # Advances ReplayClock BEFORE emitting each bar.
```

Critical ordering: clock.advance(bar.timestamp) THEN await bus.publish(bar).
Never await between these two operations. Look-ahead bias if reversed.

### replay.py

StrategyReplaySession (watch mode):
Full D04 -> D05 -> D06-SimBroker pipeline at human-watchable speed.
User observes; model trades. Useful for visual validation of signals before trusting live.

```python
class StrategyReplaySession:
    async def start(self, speed: float = 10.0) -> None: ...
    async def pause(self) -> None: ...
    async def resume(self) -> None: ...
    async def set_speed(self, multiplier: float) -> None: ...
    async def jump_to(self, dt: datetime) -> None: ...
```

ManualReplaySession (trader training mode):
Same pipeline but DecisionEngine is silenced. D04 indicators visible.
User places trades via UI. D06-SimBroker handles them. Scorer tracks performance.

```python
class ManualReplaySession:
    async def start(self) -> None: ...
    async def step(self) -> None: ...              # advance one primary TF bar
    async def step_multiple(self, n: int) -> None: ...
    async def place_order(self, side: OrderSide, size: float) -> Order: ...
    async def close_position(self, instrument: Instrument) -> Order: ...
    async def end_session(self) -> ReplayReport: ...
```

### session_state.py
Thread-safe shared state between replay session and WebSocket emitter.
```python
class ReplaySessionState:
    mode: str          # "watch" | "manual"
    status: str        # "running" | "paused" | "ended"
    current_time: datetime
    current_bar_index: int
    total_bars: int
    speed: float
    instrument: Instrument
    open_positions: list[PositionSummary]
    trade_history: list[Order]
    current_portfolio: PortfolioState
```

### scorer.py
Manual replay performance metrics at session end:
- Win rate, profit factor, average R:R, max drawdown
- vs. model performance on the same period (runs StrategyReplaySession in parallel for comparison)
- vs. buy-and-hold benchmark
- Discipline score: did user respect SL levels? Average hold time vs optimal?

### reporter.py
Unified report for all three modes.
Outputs:
- JSON: data/reports/{mode}_{instrument}_{start}_{end}_{uuid}.json
- HTML: embedded Plotly charts (equity curve, drawdown, trade distribution)
- Console: summary stats table

Cleanup policy: auto-delete reports older than 30 days OR keep last 50 runs. Configurable.

### websocket.py
Emits ReplayFrame to D10's WebSocket endpoint at each bar advance.
ReplayFrame contains: current bar OHLCV, last TechnicalSignal, last TradeSignal,
current PortfolioState, session_state (bar index, speed, status).
Only instantiated when D10 backend is running. Zero coupling otherwise.

---

## Existing Code to Migrate

| Existing | Action |
|---|---|
| src/backtest/engine.py | Refactor: accept DataFeed + isolated bus; keep core logic |
| src/backtest/walk_forward.py | Minimal: wire to DataFeed; keep algorithm |
| src/backtest/cpcv.py | Keep unchanged; algorithm is correct |

---

## Testing Strategy
Coverage target: 65%.

Unit:
- feed.py: fixture data -> bars in chronological order; clock advances to each timestamp
- session_state.py: thread safety under concurrent reads + one writer
- scorer.py: known trade list -> correct win rate, profit factor, drawdown

Integration:
- Auto backtest: EUR/USD 2022 fixture -> full pipeline -> report with expected fields
- Strategy replay: speed=0; 100 bars emitted; portfolio state correct at bar 100
- Manual replay: simulate place_order() calls; end_session() -> report with correct metrics
- ISOLATION TEST: subscribe to production bus; run full replay; assert ZERO events on production bus

Performance:
- Auto backtest, 5 years data, 4 instruments, 3 timeframes: complete under 5 minutes

---

## Implementation Phases

### Phase 2a (MASTER Phase 2)
1. Write feed.py — bar feeder with ReplayClock integration; streaming Parquet reads
2. Refactor engine.py — accept DataFeed + isolated bus
3. Verify cpcv.py and walk_forward.py pass existing tests
4. Write runner.py — auto mode only
5. Milestone: auto backtest on EUR/USD 2022 fixture; prints stats to console

### Phase 2b
6. Write replay.py — StrategyReplaySession
7. Write session_state.py
8. Write reporter.py — JSON + console first
9. Write websocket.py stub (no-op until D10 exists)
10. Milestone: strategy replay runs at 10x from CLI. **Technical-only at this point —
    D03 doesn't exist yet, so D05's fusion always sees fundamental=None during this
    milestone. This is the correct and expected state for Phase 2, not a shortfall.**

### Phase 3 follow-on (once D03 exists, MASTER Phase 3)
10b. Add D03 FundamentalAgent instantiation to runner.py's setup sequence, fed from
     D02's historical news/calendar store rather than live polling
10c. Re-run the Phase 2 fixture replay with D03 wired in; confirm FundamentalSignal
     events now appear in the replay bus log and influence D05's fused output where
     a relevant historical news event falls within the replay window
10d. Milestone: replay shows fundamental + technical signals together, matching what
     full live trading will look like once D03 ships

### Phase 5 (when D10 Web UI ready)
11. Activate websocket.py — connect to D10 WebSocket endpoint
12. Wire replay controls to D10 API (start/pause/step/jump)
13. HTML report with Plotly charts
14. Milestone: replay visible and controllable in browser

### Phase 5b (manual replay)
15. ManualReplaySession in replay.py
16. Write scorer.py
17. Wire manual order entry to D10 UI controls
18. Milestone: user trades historical data in browser; receives scorecard

---

## Known Risks

**Replay isolation is critical.** Assert at runner.py startup: broker must be SimBroker.
Add isinstance(broker, SimBroker) assertion, not just a comment. Failing this test
must abort startup, not proceed with a warning.

**Clock control race.** advance() then publish() must be in the same coroutine with
no awaits between them. Never: await advance(); await publish(). Always: advance(); await publish().
The asyncio event loop guarantees sequential execution within one coroutine.

**Look-ahead bias.** Signal uses bar N close; execution happens at bar N+1 open.
feed.py publishes bars when they CLOSE. signal_builder.py suggested_entry targets next open.
Write an integration test that explicitly checks fill prices vs signal prices.
Any fill at exact signal-bar close price is a look-ahead bug.

**Memory with long history.** 1m data, 4 instruments, 5 years = ~100M rows.
pyarrow.dataset.Scanner mandatory for streaming. Never pd.read_parquet() the full range.

**Report file growth.** 30-day auto-delete or last-50 retention policy.
Configurable via backtest.report_retention config key.
