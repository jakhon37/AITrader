# D10 — WEBUI

## 1. Purpose & boundaries
FastAPI backend (REST + WebSocket) and React frontend using TradingView's Lightweight
Charts library. Panels: live candlestick chart with signal overlays, multi-timeframe
tabs, news feed, signal log, portfolio/P&L stats, config editor, and the replay page.
Replaces all Streamlit dashboards entirely. **Read-only against trading state**, with two
controlled exceptions: replay control commands (proxied to D08) and config edits
(proxied to D01's config loader). **Never writes a live trade directly** — that path only
exists through D05 → D06.

## 2. Dependencies
D01 (bus, for live signal push over WebSocket), D02 (historical reads for chart
backfill), D06 (portfolio/fill state for the P&L panel), D08 (replay control, replay
page only). **Never imports D03 or D04 directly** — live fundamental/technical signals
reach the UI exclusively via the D01 bus subscription in the backend.

## 3. Emits / exposes
HTTP/WebSocket endpoints, not bus topics:
- REST: historical OHLCV, signal history, trade log, config read/write
- WebSocket: live price ticks, live signal pushes (fundamental/technical/trade), fill events
- Replay control endpoints: play/pause/step/speed/jump-to-date, scorecard read (manual
  replay mode) — all proxy directly to D08's API from section 3 of that division's MD

## 4. Internal module structure
```
src/api/                       # backend — refactor of existing placeholder
  main.py                        # FastAPI app, composition root wiring (bus injection etc.)
  routes/
    market.py                      # historical OHLCV REST
    signals.py                       # signal history REST
    portfolio.py                       # portfolio/P&L REST, reads D06 state
    replay.py                            # proxies to D08 replay control API
    config.py                              # instrument/strategy config read/write
  ws/
    live_feed.py                             # WebSocket — subscribes to D01 bus, pushes to clients

frontend/                       # new React app
  components/
    Chart.tsx                     # Lightweight Charts wrapper, candlestick + overlays
    SignalLog.tsx                   # timestamped fundamental/technical/trade signal log
    NewsFeed.tsx                      # live scrolling, sentiment-colored
    PortfolioPanel.tsx                  # P&L, open positions, paper trading stats
    ConfigEditor.tsx                      # instrument selection, strategy parameters
    ReplayControls.tsx                      # play/pause/step/speed, manual trade buttons,
                                               # scorecard display, prominent "REPLAY MODE" banner
```

## 5. Existing code to migrate
`src/api/` currently exists as an unwired placeholder per the AGENTS.md package layout —
this division is effectively greenfield despite the directory already existing.

## 6. Testing strategy
**Coverage target: 50%**.
- WebSocket push integration tests: confirm bus events reach connected clients with
  correct schema, and that disconnection/reconnection doesn't drop or duplicate messages
- REST contract tests: every endpoint response validated against the matching
  `CONTRACTS.md` schema, not just "returns 200"
- Replay control proxy tests: commands sent from the UI reach D08 and the resulting
  state changes (VirtualClock position, scorecard updates) are reflected back correctly

## 7. Implementation phases (internal)
1. REST historical endpoints — Phase 5, week 1
2. WebSocket live feed (subscribing to D01 bus) — Phase 5, week 1–2
3. React shell + Lightweight Charts integration — Phase 5, week 2
4. Remaining panels: news feed, signal log, portfolio, config editor — Phase 5, week 2–3
5. Replay page wired to D08 — Phase 5, week 3

## 8. Known risks & gotchas
- **WebSocket reconnect/backpressure** — a slow or disconnected client shouldn't block
  the bus subscription for other clients; buffer and drop policy needs to be explicit.
- **Chart performance** — years of historical bars plus live overlay updates can choke
  a naive Lightweight Charts setup; use its built-in data windowing rather than pushing
  the full history into the DOM at once.
- **Replay/live state confusion is a real safety concern, not just UX polish.** The
  replay page must make it visually unmistakable that you're looking at historical
  playback, not live market state — a prominent banner and distinct color treatment,
  not a subtle label.
