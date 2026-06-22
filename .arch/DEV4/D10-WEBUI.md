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
  replay mode) — all proxy directly to D08's API.

## 4. Internal module structure
```
src/api/                       # backend — refactor of existing placeholder
  __init__.py
  main.py                      # FastAPI app setup, CORS, bus dependency injection
  ws/
    manager.py                 # manages WebSocket subscriber lists
    handlers.py                # receives D01 bus signals, pushes to WebSocket manager
  routes/
    market.py                  # historical OHLCV endpoints
    signals.py                 # REST endpoint to query past signals
    portfolio.py               # REST endpoint for active positions and balances
    config.py                  # handles strategy and instrument config updates
    replay.py                  # proxy endpoints to D08's replay session API
    health.py                  # checks division health status

frontend/                      # new React app
  package.json
  src/
    main.tsx
    App.tsx
    components/
      Chart/
        CandleChart.tsx        # Lightweight Charts wrapper (candles + trade execution markers)
        SignalOverlay.tsx      # indicator subplots below main chart
      Panels/
        SignalLog.tsx          # displays live scrolling system signals
        NewsFeed.tsx           # scrolling fundamental news, sentiment-colored
        PortfolioPanel.tsx     # balance, equity, positions, daily P&L stats
        ConfigEditor.tsx       # instrument settings and parameters editor
      Replay/
        ReplayControls.tsx     # controls play/pause/step, manual trade entry buttons
        ReplayScorecard.tsx    # displays performance and score metrics at session end
```

## 5. Existing code to migrate
`src/api/` currently exists as an unwired placeholder — this division is effectively greenfield.

## 6. Testing strategy
**Coverage target: 50%**.
- WebSocket integration: verify that signals emitted on the bus are pushed to connected WebSocket clients in real-time.
- Proxy validation: verify that REST replay commands submitted on `/api/replay/*` successfully forward to D08 and modify the `VirtualClock` timestamp.
- DOM leak check: check that rendering long candle histories does not leak DOM memory in React.

## 7. Implementation phases (internal)
1. REST historical endpoints — Phase 5, week 1
2. WebSocket live feed (subscribing to D01 bus) — Phase 5, week 1–2
3. React shell + Lightweight Charts integration — Phase 5, week 2
4. Remaining panels: news feed, signal log, portfolio, config editor — Phase 5, week 2–3
5. Replay page wired to D08 — Phase 5, week 3

## 8. Known risks & gotchas
- **Replay/Live State Cues:** Replay screens must be visually distinct to prevent operator error. Use a prominent, flashing "REPLAY MODE" banner, a distinct background shade, and block live trade buttons when the replay screen is open.
- **WebSocket buffer overflow:** Rapid price events can overload WebSocket channels. Buffer updates and drop slow client sessions if the queue fills up.
- **Lightweight Charts data scaling:** Pushing thousands of historical bars into the DOM will crash browsers. Implement chart windowing to display only visible candles.
