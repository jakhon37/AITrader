# D10 — WEBUI

## Purpose
Professional trading terminal UI. FastAPI backend with WebSocket push for real-time data;
React + TradingView Lightweight Charts frontend. Replaces all Streamlit dashboards.
Also serves as the control surface for D08 replay (start/pause/step/manual trade entry).

Does NOT: produce signals, execute trades, or run analysis. Read-only access to system
state via the signal bus and D02/D06 query APIs. Never imports from D03, D04, or D05 directly.

---

## Dependencies
- D01-CORE: contracts, bus (subscribe to live signal channels), config, logging
- D02-DATA: DataStore query API (historical OHLCV, news, calendar)
- D06-EXECUTION: PortfolioState reads; position and order history query
- D08-BACKTEST: replay session control API (programmatic, not bus)

D10 reads bus signals for live display but never publishes to the bus.
D10 never imports from D03 or D04 — their signals arrive via bus subscriptions.

---

## Emits
Nothing onto the signal bus. WebSocket pushes to browser clients only.

---

## Internal Module Structure

```
src/api/                   <- FastAPI backend (refactor existing placeholder)
  __init__.py
  main.py                  <- app factory; mounts all routers; starts bus subscriptions
  ws/
    manager.py             <- WebSocket connection manager; broadcasts to all connected clients
    handlers.py            <- bus subscribers that push events to WebSocket manager
  routes/
    data.py                <- GET historical OHLCV, news, calendar, economic events
    signals.py             <- GET signal history (F, T, Trade signals logged to store)
    portfolio.py           <- GET portfolio state, order history, P&L
    config.py              <- GET/PUT instrument config, strategy parameters
    replay.py              <- POST replay start/stop/pause/step; GET session state
    health.py              <- GET division health (proxies D11)
  middleware.py            <- CORS, request logging, error handling

frontend/                  <- React application
  package.json
  src/
    main.tsx
    App.tsx
    components/
      Chart/
        CandleChart.tsx    <- Lightweight Charts wrapper; handles OHLCV + overlays
        SignalOverlay.tsx  <- renders signal markers on chart
        IndicatorPanel.tsx <- RSI, MACD subplots below main chart
      Panels/
        SignalLog.tsx      <- live scrolling signal log (F + T + Trade)
        NewsFeed.tsx       <- fundamental news feed, sentiment-colored
        Portfolio.tsx      <- balance, equity, open positions, P&L
        ConfigEditor.tsx   <- instrument selection, strategy weights
      Replay/
        ReplayControls.tsx <- play/pause/speed/step/jump controls
        ReplayScore.tsx    <- scorecard for manual replay session
      Layout/
        TradingTerminal.tsx <- main layout; panel grid
        Sidebar.tsx
        Header.tsx
    hooks/
      useWebSocket.ts      <- WebSocket connection + reconnect logic
      useChartData.ts      <- OHLCV + signals for chart
      usePortfolio.ts      <- portfolio state subscription
    store/
      signals.ts           <- Zustand store for signals state
      portfolio.ts
      replay.ts
    api/
      client.ts            <- typed fetch wrappers for all REST endpoints
```

### WebSocket Design
Single WebSocket endpoint: /ws
Message types (JSON, discriminated by `type` field):
```typescript
type WsMessage =
  | { type: "ohlcv_bar";          data: OHLCVBar }
  | { type: "technical_signal";   data: TechnicalSignal }
  | { type: "fundamental_signal"; data: FundamentalSignal }
  | { type: "trade_signal";       data: TradeSignal }
  | { type: "order_event";        data: OrderEvent }
  | { type: "portfolio_update";   data: PortfolioState }
  | { type: "system_health";      data: SystemHealthEvent }
  | { type: "replay_frame";       data: ReplayFrame }
```

All live bus events are forwarded to connected WebSocket clients.
ws/handlers.py subscribes to all relevant bus channels and calls manager.broadcast().

### Chart Component (TradingView Lightweight Charts)
Library: @tradingview/lightweight-charts (MIT license, open source).
NOT the TradingView embed iframe — the standalone open-source charting engine.

CandleChart.tsx responsibilities:
- Initialize IChartApi + ICandlestickSeriesApi on mount
- Populate historical data from REST API (GET /api/data/ohlcv)
- Subscribe to WebSocket ohlcv_bar messages -> chart.update(bar) for real-time ticks
- Render signal markers: TradeSignal -> colored arrow marker at bar timestamp
- Render TechnicalSignal entry/SL/TP as horizontal price lines
- TF tab switcher: changing TF fetches new historical data + re-subscribes for that TF's bars
- Replay mode: chart advances bar by bar from ReplayFrame WebSocket messages

IndicatorPanel.tsx:
- RSI subplot below main chart (separate pane)
- MACD histogram subplot
- Data sourced from TechnicalSignal.per_timeframe[primary_tf].indicators

### Main Layout
```
+--------------------+----------------------------+------------------+
|                    |                            |  Signal Summary  |
|  Candlestick Chart | Indicator Panel (RSI/MACD) |  Fund: Bearish   |
|  + signal markers  |                            |  Tech: Bullish   |
|  TF tabs: 1H 4H 1D |                            |  Trade: Neutral  |
+----------+---------+----------------------------+------------------+
|          |         |                            |  Portfolio Stats |
|  News    | Signal  |     Trade Log              |  Balance: ...    |
|  Feed    |  Log    |  (open positions + history)|  P&L: ...        |
|  (sent.) |         |                            |  Drawdown: ...   |
+----------+---------+----------------------------+------------------+
Config bar: [Instrument selector] [TF selector] [Mode: Paper/Live] [Settings]
```

Replay page is a separate route (/replay) with:
- Same chart component but driven by ReplayFrame messages
- Replay controls panel (play/pause/speed slider/step/jump-to-date)
- For manual mode: Buy/Sell buttons + size input + close position button
- Session scorecard panel (appears at session end)

### Config Editor
Renders current instrument config from GET /api/config/{instrument}.
Editable fields: active_timeframes, fundamental_weight, technical_weight, min_confidence.
PUT /api/config/{instrument} saves to instruments.yaml and hot-reloads config in D05.

---

## Existing Code to Migrate

| Existing | Action |
|---|---|
| src/api/ (placeholder) | Build out as full FastAPI app |
| dashboards/paper_monitor.py | Delete once D10 Panel.Portfolio + Trade Log is complete |
| dashboards/feature_explorer.py | Delete once D10 IndicatorPanel is complete |

---

## Technology Choices

| Concern | Choice | Why |
|---|---|---|
| Charting | TradingView Lightweight Charts | Open source MIT; WebSocket-native; professional candlestick; custom overlays |
| Frontend framework | React + TypeScript | Component model fits panel-based trading UI |
| State management | Zustand | Lightweight; WebSocket update pattern fits well |
| Styling | Tailwind CSS | Utility-first; dark theme trivial |
| Backend | FastAPI | Async-native; WebSocket support; OpenAPI docs auto-generated |
| WS client | native browser WebSocket + reconnect hook | No extra library needed |

NOT using: D3/canvas for charts (too much work, worse output), Redux (overkill for this),
Streamlit (WebSocket limitations, no custom layout), any paid charting library.

---

## Testing Strategy
Coverage target: 50% backend; frontend tested via Playwright E2E.

Backend unit:
- ws/manager.py: connect, broadcast, disconnect lifecycle
- ws/handlers.py: mock bus event -> WebSocket message emitted with correct type field
- routes/data.py: GET /api/data/ohlcv returns correct Parquet data for date range
- routes/replay.py: POST start -> runner.start() called; GET session -> correct state

Frontend E2E (Playwright):
- Chart renders with historical data on load
- New bar arrives via WebSocket -> chart updates without flicker
- Signal marker appears on chart when TradeSignal published
- TF tab switch -> chart reloads with correct data
- Replay: play/pause controls work; bar count increments; chart advances

---

## Implementation Phases

### Phase 5a (MASTER Phase 5)
1. Set up FastAPI app structure (src/api/)
2. Write ws/manager.py and ws/handlers.py (bus -> WebSocket bridge)
3. Write routes/data.py and routes/portfolio.py
4. Write routes/health.py
5. Set up React + TypeScript + Tailwind project (frontend/)
6. Install @tradingview/lightweight-charts
7. Build CandleChart.tsx — historical load + WebSocket update
8. Build Header.tsx, Sidebar.tsx, TradingTerminal.tsx layout
9. Build Portfolio.tsx panel
10. Milestone: live candlestick chart in browser receiving real WebSocket ticks

### Phase 5b
11. Build SignalLog.tsx — live scrolling signal events
12. Build NewsFeed.tsx — sentiment-colored news stream
13. Build IndicatorPanel.tsx — RSI + MACD subplots
14. Build ConfigEditor.tsx
15. Delete dashboards/paper_monitor.py and feature_explorer.py
16. Milestone: full trading terminal layout; all panels live; Streamlit decommissioned

### Phase 5c (Replay UI)
17. Write routes/replay.py
18. Build Replay/ components: ReplayControls, ReplayScore
19. Wire ReplayFrame WebSocket messages to chart advancement
20. Manual replay: Buy/Sell UI -> POST /api/replay/order
21. Milestone: replay controllable in browser; manual trades work; scorecard shown

---

## Known Risks

**WebSocket reconnection.** Browser tabs disconnect on sleep/network loss. useWebSocket.ts
must implement exponential backoff reconnect. On reconnect, fetch current state via REST
(don't assume WebSocket messages cover the gap).

**Chart performance with many signals.** If 1000+ signal markers are drawn on the chart,
Lightweight Charts performance degrades. Implement: only render markers visible in current
viewport; prune markers older than 200 bars from the visible set.

**Config hot-reload.** PUT /api/config/{instrument} must safely reload InstrumentConfig
in D05 without interrupting live trading. Use asyncio.Lock around config reads in D05.
Test: config change during active paper trading session.

**Replay frame rate.** At 100x replay speed, the backend emits frames faster than the
browser can render (60fps limit). Backend should batch frames when speed > 60x:
send one WebSocket message per second with the latest bar rather than all bars.

**CORS in development.** Frontend at :3000, FastAPI at :8000 in dev. Configure CORS
middleware in FastAPI to allow localhost:3000. In production, frontend is served by
FastAPI as a static build — no CORS issue.

**Sensitive data in WebSocket.** PortfolioState includes balance and P&L.
If the trading terminal is ever deployed with multi-user access, add authentication
(JWT token on WS handshake). For single-user personal use, basic API key in header
is sufficient. Plan for this before any cloud deployment.
