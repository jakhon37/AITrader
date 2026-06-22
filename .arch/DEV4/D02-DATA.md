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
- Historical OHLCV range query (`DataStore.get_ohlcv`)
- News article range query (`DataStore.get_news`)
- Calendar event range query (`DataStore.get_economic_events`)
- Model registry read/write (artifacts written by D09, read by D05 per CONTRACTS.md `ModelArtifact` via `registry_store.py`)

## 4. Internal module structure
```
src/data/
  __init__.py
  scheduler.py        # fires candle-close + news-poll events onto bus (checks VirtualClock)
  store/
    parquet_store.py  # storage abstraction for OHLCV parquet storage
    registry_store.py # model artifact read/write (decoupled model storage handoff)
  loaders/
    csv_loader.py     # existing — OHLCV from file
    live_data.py      # existing — refactor to publish onto bus instead of returning df
  sources/
    news_fetcher.py   # NewsAPI + RSS polling
    calendar.py       # Forex Factory economic calendar scraper
    fred.py           # FRED API macro series fetcher
  validation.py       # OHLCV schema checks (no NaN, monotonic timestamps, OHLC consistency)
```

## 5. Existing code to migrate
- `src/data/loaders/csv_loader.py` — keep, wrap with the new store abstraction
- `src/data/loaders/live_data.py` — refactor from "fetch and return" to "fetch and publish"

## 6. Testing strategy
**Coverage target: 50%** (default gate).
- Fetch failure tests: network errors, malformed responses, and rate-limit errors must
  raise exceptions and surface to D11 — never silently return an empty DataFrame.
- Schema validation: every fetched bar/article/event validates against its `CONTRACTS.md`
  model before storage or publish.
- Store abstraction: round-trip write/read tests independent of backend choice.

## 7. Implementation phases (internal)
1. OHLCV refactor + Parquet store abstraction — Phase 1, week 1
2. Economic calendar fetch + store — Phase 1, week 1–2
3. News ingestion — Phase 1, week 2 (raw fetch only; D03 adds sentiment later)
4. Registry store read/write API — ready before Phase 6 (D09 needs to write to it)

## 8. Known risks & gotchas
- **Timezone normalization at boundary:** Timezones differ across Yahoo Finance, FRED, and news RSS feeds. Timezones must be converted to UTC immediately at the fetch boundary.
- **Scraper Fragility:** Forex Factory scrapers break when website layouts change. Failures in scrapers must raise alerts to D11 but not halt execution of price-bar scheduler.
- **API Rate Limits:** yfinance live requests can trigger temporary bans. NewsAPI quota limits must degrade gracefully (reducing polling rates) rather than crashing.
