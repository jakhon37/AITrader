# D08 — BACKTEST

## 1. Purpose & boundaries
Three modes of the same core idea: automated backtest (CPCV, walk-forward), strategy
replay (watch the system run on history), and manual replay (you trade against history,
scored like the model would be). Replay is not a separate architectural concern from
backtesting — it's backtesting with a human or a visual layer in the loop. **Offline
only, never runs in the live process.** Reuses D06's `SimBroker` unchanged.

## 2. Dependencies
D01 (for `VirtualClock` control — the only division allowed to call `set_replay_time`,
`advance`, `reset_to_live`), D02 (historical OHLCV, news, calendar), D03 (fundamental
signals — **wired in Phase 3**, since D03 doesn't exist until then; Phase 2's replay
milestone is technical-only by necessity, not by design choice), D04 (technical
signals), D06's `SimBroker` (reused for trade fills and P&L tracking).

## 3. Emits / exposes
No live bus topics. In replay/watch mode, drives the **same bus** with historical signals
(via the VirtualClock-controlled time source) so that D10's replay UI page can render
them through the normal live-signal rendering path — no separate replay-specific UI
plumbing needed on the frontend side. Produces backtest reports/artifacts to disk.

Direct API (consumed by D10's replay page):
* POST `/api/replay/start` (parameters: instrument, start, end, speed, mode)
* POST `/api/replay/pause` / `/api/replay/resume`
* POST `/api/replay/step` (advances clock by 1 candle step)
* POST `/api/replay/speed` (adjusts time multiplier)
* POST `/api/replay/order` (place manual order during replay)
* GET `/api/replay/scorecard` (yields metrics: win rate, profit factor, drawdown, discipline)

## 4. Internal module structure
```
src/backtest/
  __init__.py
  engine.py           # existing — standard backtest logic (refactored to accept DataFeed)
  walk_forward.py     # existing — walk-forward validator
  cpcv.py             # existing — Combinatorial Purged Cross-Validation
  feed.py             # bar-by-bar data feeder; manages ReplayClock step ordering
  replay.py           # NEW — StrategyReplaySession & ManualReplaySession logic
  scorer.py           # evaluates manual replay trades, computes discipline scorecard
  reporter.py         # writes JSON reports and Plotly html visual curves
```

## 5. Existing code to migrate
`engine.py`, `walk_forward.py`, `cpcv.py` — all existing and reused largely as-is. `feed.py`, `replay.py`, `scorer.py` are new.

## 6. Testing strategy
**Coverage target: 50%**.
- Replay determinism: same seed + same historical window must produce identical signal timings, fills, and scorecards.
- Scoring accuracy: test scorecard calculations against a predefined sequence of mock trades.
- Replay Isolation check: verify that running a replay publishes ZERO events onto production/live bus channels.

## 7. Implementation phases (internal)
1. Replay engine + VirtualClock control wiring — Phase 2, week 1
2. Automated backtest refactor (existing CPCV/walk-forward, no major rewrite) — Phase 2, week 1–2
3. Manual replay mode (human trade entry + scorecard) — Phase 2, week 2–3
4. Fundamental-signal replay support — Phase 3, once D03 exists

## 8. Known risks & gotchas
- **Lookahead bias:** The replay sequence must advance the `VirtualClock` *before* publishing the price bar to the bus. Correct ordering is non-negotiable: `clock.advance(bar.timestamp) THEN await bus.publish(bar)`. Any deviation causes lookahead bias.
- **System Seeding:** Random slippage, models, and execution weights must be seeded to guarantee repeatable backtests.
- **Data Scaling:** Large backtests can cause memory crashes. Use `pyarrow.dataset.Scanner` to stream data from Parquet files page-by-page.
