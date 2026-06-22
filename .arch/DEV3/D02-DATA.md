# D02 — DATA

## 1. Purpose & boundaries
All data ingestion, normalization, and storage: OHLCV price data, news articles, economic
calendar events, macro series (FRED). Owns the canonical Parquet/file store and the model
registry directory. Fires `data.bar.*` events onto the bus on candle close, and serves
historical reads to D08 and D10. **No analysis** — no sentiment scoring (D03), no
indicator computation (D04). DATA fetches, validates, stores, serves. Nothing else.

## 2. Dependencies
D01 only.

## 3. Emits / exposes
Bus topics:
- `data.bar.{instrument}.{timeframe}` — on candle close, per active timeframe
- `data.news.raw.{instrument}` — on new article ingested
- `data.calendar.event.{instrument}` — on calendar event detected/updated

Direct read API (used by D08 replay, D09 training, D10 historical charts):
- historical OHLCV range query
- news article range query
- calendar event range query
- model registry read (artifacts written by D09, per CONTRACTS.md `ModelArtifact`)

## 4. Internal module structure
```
src/data/
  loaders/
    csv_loader.py        # existing — OHLCV from file
    live_data.py          # existing — refactor to publish onto bus instead of returning df
  news/
    fetcher.py            # NewsAPI + RSS polling
  calendar/
    ff_fetcher.py          # Forex Factory economic calendar
    fred_fetcher.py        # FRED macro series
  store/
    parquet_store.py       # storage abstraction — swappable backend (Parquet now, InfluxDB later)
    registry_store.py      # model artifact read/write, used by D09 (write) and D05 (read)
  scheduler.py              # fires candle-close + news-poll events onto bus
```

## 5. Existing code to migrate
- `src/data/loaders/csv_loader.py` — keep, wrap with the new store abstraction
- `src/data/loaders/live_data.py` — refactor from "fetch and return" to "fetch and publish"

## 6. Testing strategy
**Coverage target: 50%** (default gate).
- Fetch failure tests: network errors, malformed responses, and rate-limit errors must
  raise exceptions and surface to D11 — never silently return an empty DataFrame
- Schema validation: every fetched bar/article/event validates against its `CONTRACTS.md`
  model before storage or publish
- Store abstraction: round-trip write/read tests independent of backend choice

## 7. Implementation phases (internal)
1. OHLCV refactor + Parquet store abstraction — Phase 1, week 1
2. Economic calendar fetch + store — Phase 1, week 1–2
3. News ingestion — Phase 1, week 2 (raw fetch only; D03 adds sentiment later)
4. Registry store read/write API — ready before Phase 6 (D09 needs to write to it)

## 8. Known risks & gotchas
- **yfinance rate limits** under live polling — needs backoff and a fallback data source
  for production, not just dev.
- **NewsAPI free tier limits** — design the fetcher to degrade gracefully (reduce poll
  frequency) rather than crash when the quota is hit.
- **Forex Factory has no official API** — scraping is fragile. Treat the calendar fetcher
  as the most likely thing to break and isolate it so a failure doesn't take down OHLCV
  ingestion too.
- **Timezone handling** — every source returns timestamps in different formats/zones.
  Normalize to UTC at the ingestion boundary, never downstream.
