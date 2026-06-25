# D02 — DATA

## Purpose
Single source of truth for all raw data. Owns: OHLCV ingestion and storage,
news article ingestion, economic calendar fetching, macro data (FRED),
candle-close event scheduling, and the data access layer for all other divisions.

Does NOT: score sentiment, compute indicators, or interpret data meaning.
Fetch, validate, store, serve — nothing else.

---

## Dependencies
- D01-CORE: contracts, bus, clock, config, logging

## Instrument activation
Which pairs the scheduler polls, auto-refresh backfills, and the chart UI lists comes from
`enabled: true` on each block in `config/instruments.yaml` (via `get_enabled_instruments()`).
Do **not** maintain a second instrument list in `dev.yaml` — env YAML holds pipeline cadence
(`data.pipeline.*`) only.

Session hours and gold `daily_break` in instruments.yaml drive chart bar filtering via
`src/core/session.py` (loaded through `load_instruments()`).

---

## Emits
| Channel | Type | When |
|---|---|---|
| BusChannel.OHLCV_BAR | OHLCVBar | On each confirmed candle close |
| BusChannel.ECONOMIC_EVENT | EconomicEvent | 60 min before event, then at release with actuals |

Exposes direct query API for historical reads:
- DataStore.get_ohlcv(instrument, timeframe, start, end) -> pd.DataFrame
- DataStore.get_news(instrument, start, end) -> list[NewsArticle]
- DataStore.get_economic_events(start, end, impact_filter) -> list[EconomicEvent]

---

## Internal Module Structure

```
src/data/
  __init__.py
  scheduler.py      <- candle-close timer; fires OHLCVBar per TF close
  store.py          <- DataStore; unified query over Parquet + SQLite news/calendar
  loaders/
    csv_loader.py   <- existing; refactor to emit OHLCVBar
    live_data.py    <- existing; yfinance; refactor to use VirtualClock
    oanda.py        <- future live feed stub (raises NotImplementedError)
  sources/
    news_fetcher.py <- NewsAPI + RSS ingestion
    calendar.py     <- Forex Factory economic calendar
    fred.py         <- FRED API macro data
  models.py         <- internal: NewsArticle, RawCalendarEvent (not in contracts)
  validation.py     <- OHLCV schema checks (no NaN, monotonic timestamps, OHLC consistency)
```

### scheduler.py
Async loop. For each active (instrument, timeframe) pair, calculates next candle close.
Live mode: wall-clock sleep until close. Replay mode: checks clock.now() on each tick,
emits when virtual time crosses candle boundary. No wall-clock sleep in replay.

### store.py
Storage backends:
- OHLCV: Parquet, partitioned by {instrument}/{timeframe}/YYYY-MM.parquet
- News: SQLite — articles(id, instrument, headline, url, published_at, source)
- Calendar: SQLite — calendar(id, name, timestamp, impact, instruments, actual, forecast, previous)

### news_fetcher.py
Sources: NewsAPI (priority 1), Reuters/Bloomberg RSS (priority 2), Forex Factory (priority 3).
Deduplication: hash (headline, published_at) before insert.
Rate limiter: token bucket per source. Backoff on 429.
Background async task, default 10-minute interval.

### calendar.py
Fetches from Forex Factory or Investing.com.
Pre-release: publishes EconomicEvent with actual=None.
Post-release: updates row with actual + surprise_pct; re-publishes.
Pre-release notification fires 60 min before — D06 uses this to activate news_halt window.

### fred.py
FRED API client. Series: DFF, CPIAUCSL, UNRATE, T10Y2Y.
Fetched weekly Sunday UTC 00:00. Stored in SQLite.

---

## Existing Code to Migrate

| Existing file | Action |
|---|---|
| src/data/loaders/csv_loader.py | Keep core; add schema validation; emit OHLCVBar |
| src/data/loaders/live_data.py | Keep yfinance logic; wire to scheduler; use VirtualClock |
| scripts/download_sample_data.py | Keep; update to Parquet format if not already |

---

## Environment Variables Required
```
NEWSAPI_KEY   # NewsAPI.org; free tier sufficient for dev
FRED_API_KEY  # FRED (St. Louis Fed); free
```

---

## Testing Strategy
Coverage target: 65%.

Unit: validation.py OHLCV pass/fail; csv_loader fixture; store write/read round-trip;
news_fetcher mock HTTP + dedup; calendar pre/post-release event publishing.
Integration: live_data.py with pytest.mark.live (skip in CI unless LIVE_DATA=1);
candle-close cycle: scheduler fires -> OHLCVBar published -> subscriber receives.

---

## Implementation Phases

### Phase 1 (MASTER Phase 1)
1. Create src/data/ structure; write validation.py
2. Refactor csv_loader.py -> validated OHLCVBar output
3. Refactor live_data.py -> wired to scheduler, uses VirtualClock
4. Write store.py — OHLCV Parquet layer
5. Write scheduler.py — live mode
6. Run existing test_real_data_if_available; confirm no regression

### Phase 1b (when D03 starts)
7. Write news_fetcher.py; write calendar.py
8. Add news + calendar SQLite layers to store.py
9. Wire EconomicEvent bus publishing

### Phase 1c (Phase 4+)
10. Write fred.py; add macro series to store

---

## Known Risks

**Forex Factory TOS.** Scraping may violate terms. Evaluate paid calendar API as fallback.
**yfinance reliability.** Design live_data.py with source abstraction for easy swap.
**Parquet append.** Use monthly partitioning; append-only within current month.
**News volume.** Rate-limit at ingestion; only deduped events hit the bus.
**Time zones.** Normalize ALL timestamps to UTC with tzinfo=timezone.utc before any store write.
