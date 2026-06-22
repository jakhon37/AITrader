# D08 — BACKTEST

## 1. Purpose & boundaries
Three modes of the same core idea: automated backtest (CPCV, walk-forward), strategy
replay (watch the system run on history), and manual replay (you trade against history,
scored like the model would be). Replay is not a separate architectural concern from
backtesting — it's backtesting with a human or a visual layer in the loop. **Offline
only, never runs in the live process.** Reuses D06's `SimBroker` unchanged.

## 2. Dependencies
D01 (for `VirtualClock` control — the only division allowed to call `set_replay_time`,
`advance`, `reset_to_live`), D02 (historical OHLCV, news, calendar), D04 (technical
signals), D03 (fundamental signals — **wired in Phase 3**, since D03 doesn't exist until
then; Phase 2's replay milestone is technical-only by necessity, not by design choice),
D06's `SimBroker`.

## 3. Emits / exposes
No live bus topics. In replay/watch mode, drives the **same bus** with historical signals
(via the VirtualClock-controlled time source) so that D10's replay UI page can render
them through the normal live-signal rendering path — no separate replay-specific UI
plumbing needed on the frontend side. Produces backtest reports/artifacts to disk.

Direct API (consumed by D10's replay page): play / pause / step / set-speed / jump-to-date
/ get-scorecard (for manual replay mode).

## 4. Internal module structure
```
src/backtest/
  engine.py            # existing — standard backtest logic
  walk_forward.py         # existing — walk-forward validator
  cpcv.py                    # existing — Combinatorial Purged Cross-Validation
  replay.py                    # NEW — bar-by-bar feed via VirtualClock, speed control,
                                  # pause/resume, jump-to-date; drives D03/D04 to emit
                                  # signals against historical bars exactly as they would live
  manual_replay.py               # NEW — silences the model, accepts human buy/sell input via
                                    # D10's UI, scores performance (P&L, win rate, max DD, avg RR)
  reports/                         # backtest output: metrics, equity curves, trade logs
```

## 5. Existing code to migrate
`engine.py`, `walk_forward.py`, `cpcv.py` — all existing and reused largely as-is for the
automated backtest mode. `replay.py` and `manual_replay.py` are new.

## 6. Testing strategy
**Coverage target: 50%**.
- CPCV split correctness: verify purge/embargo logic against known small datasets
- Replay determinism: same seed + same historical window → identical run, every time
  (required for fair manual-replay skill scoring and for reproducible debugging)
- Manual replay scorecard math: P&L, win rate, max drawdown, average RR computed
  correctly against a scripted sequence of manual trades

## 7. Implementation phases (internal)
1. Replay engine + VirtualClock control wiring — Phase 2, week 1
2. Automated backtest refactor (existing CPCV/walk-forward, no major rewrite) — Phase 2, week 1–2
3. Manual replay mode (human trade entry + scorecard) — Phase 2, week 2–3
4. Fundamental-signal replay support — Phase 3, once D03 exists

## 8. Known risks & gotchas
- **Lookahead bias** is the single highest-stakes risk here — replay must never expose
  a future bar to D03/D04/D05 before its VirtualClock timestamp arrives. This is the same
  concern flagged in D04 but doubly critical here since it's the actual validation layer.
- **Performance at scale** — replaying a full year of multi-timeframe data needs to stay
  responsive for the watch-mode UI; profile early rather than discovering this in Phase 5
  when D10 tries to render it.
- **Determinism for fair skill scoring** — manual replay mode is explicitly "test my
  skills" per the original request; if two runs of the same historical window produce
  different signal timing, the scoring isn't trustworthy. Seed everything.
