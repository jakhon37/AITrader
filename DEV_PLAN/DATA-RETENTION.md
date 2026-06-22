# DATA-RETENTION.md — Multi-Timeframe Historical Storage

Reference doc for how D02-DATA acquires, stores, and maintains multi-year OHLCV
history across all active timeframes. D02's `store.py` and `loaders/` implement this
spec. D08-BACKTEST and D09-TRAINER read against it for replay and training windows.
D11-OPS's `data_probe.py` implements the periodic integrity check defined here.

This is not a new division — it's the detailed design behind D02's existing
"OHLCV ingestion and storage" responsibility, broken out because the source-availability
problem (below) is easy to get wrong silently and expensive to discover late.

---

## 1. The actual constraint: source retention, not storage capacity

It's worth stating plainly, because it reframes the whole problem: **storage space is
not the bottleneck here.** Two years of 1-minute EUR/USD bars is roughly 375,000 rows;
across 4 instruments and 2 years that's ~3M rows, well under 100MB even before Parquet
compression. This is a small-data problem wearing a big-data costume.

The actual constraint is that **free data sources don't retain fine-grained history very
far back**, regardless of how the query is structured. yfinance — D02's primary
source — enforces hard server-side windows per interval:

| Timeframe | Max lookback from yfinance | 2-year history from yfinance alone? |
|---|---|---|
| 1m | 7 days | No |
| 5m, 15m, 30m | 60 days | No |
| 1h | ~730 days | Yes, just barely |
| 4h | not a native interval | N/A — derived, see §6 |
| 1d, 1w | decades | Yes, trivially |

This isn't a yfinance bug — it's Yahoo's backend retention policy, and no query
parameter, retry, or pagination strategy gets around it. The design below exists
because of this fact, not in spite of bad engineering.

---

## 2. Source strategy per timeframe

| Timeframe | Authoritative source | Strategy |
|---|---|---|
| 1d, 1w | yfinance | Direct fetch, `period="max"`. Trivial, no special handling. |
| 1h | yfinance | Direct fetch, ~2 years available in one call. Refresh incrementally going forward. |
| 4h | Derived (resampled from 1h) | Never fetched directly — see §6. Computed and cached, not re-derived on every read. |
| 30m, 15m, 5m | One-time backfill (OANDA or Dukascopy) + yfinance incremental | See §5. |
| 1m | yfinance incremental only, rolling window | No long-term archive without a paid tick provider — see §5.4. |

The principle: **use the source with the deepest retention for the initial fill, then
the cheapest source (yfinance, free, already integrated) for ongoing incremental
growth.** Don't pay for a vendor feed you only need once.

---

## 3. Storage format

Parquet, columnar, via `pyarrow`. Already specified in D02-DATA.md; rationale restated
here for completeness:

- **Columnar** — a backtest reading only `close` prices for 2 years doesn't pay the I/O
  cost of `open`/`high`/`low`/`volume` it isn't using.
- **Compression** — typically 5–10x smaller than CSV for this kind of numeric series.
  Combined with the row-count estimate in §1, total footprint across all instruments,
  all timeframes, 2 years is realistically in the tens of MB, not gigabytes.
- **Schema-enforced** — no silent string/float ambiguity creeping in from a bad ingest.
- **Streamable** — `pyarrow.dataset.Scanner` lets D08's replay feed and D09's training
  pipeline read multi-year ranges without loading the full history into memory. This is
  already mandated in D08-BACKTEST.md's Known Risks; restated here because it depends
  directly on the partitioning scheme below being right.

SQLite remains correct for news and calendar data (D02's `store.py` already does this) —
that data is low-volume and benefits more from relational query flexibility than from
columnar scan speed. No change there.

---

## 4. Partitioning scheme

```
data/raw/
  {instrument}/
    {timeframe}/
      2024-01.parquet
      2024-02.parquet
      ...
```

Rules:

- **Monthly files for 1h and coarser.** A month of 1h EUR/USD bars is ~500 rows —
  small, and monthly keeps file count manageable over a 2-year archive (24 files per
  instrument/timeframe rather than 730 daily files).
- **Monthly files for 5m/15m/30m too**, despite higher row counts (a month of 5m data
  is ~6,200 rows) — still well within comfortable single-file size, and consistency
  in partitioning scheme matters more than micro-optimizing file count per timeframe.
- **Don't go finer than monthly** (e.g. daily files) unless this ever extends to tick
  data. Too many small files hurts `Scanner` read performance more than it helps
  anything — partition pruning works fine at monthly granularity for the query patterns
  D08/D09 actually run (multi-month to multi-year ranges).
- **Append-only within the current (open) month. Immutable once the month closes.**
  Already specified in D02-DATA.md. If a correction or backfill touches a closed month,
  write a new file and merge — never rewrite a closed month's file in place.

---

## 5. Backfill procedure (one-time historical import)

For 5m/15m/30m, where yfinance's 60-day window can't reach 2 years back:

### 5.1 Source
OANDA's REST API (already planned as D06's live broker, so no new vendor relationship
needed) typically offers multi-year M5/M15/M30 history on a free practice account.
Dukascopy's free historical export is a viable one-time alternative if OANDA access
isn't set up yet.

### 5.2 Job design
A standalone script, not part of the live scheduler:

```
scripts/backfill_historical.py
  --instrument EURUSD --timeframe 15m --start 2024-06-01 --end 2026-06-01
```

Requirements:
- **Idempotent.** Re-running for a range that's already backfilled should detect
  existing months in the store and skip them, not re-fetch or duplicate.
- **Resumable.** If it dies partway through a multi-year pull, the next run picks up
  from the last successfully written month, not from the start.
- **Rate-limit aware.** OANDA and Dukascopy both have request limits; the job paces
  itself rather than hammering the API and getting throttled or blocked mid-backfill.
- **Writes through the same `store.py` write path as live ingestion** (same atomic-write
  function from §7), so backfilled data and live-accumulated data are indistinguishable
  in storage — no special-cased "this came from backfill" branch anywhere downstream.

### 5.3 One-time, not recurring
This job runs once per (instrument, timeframe) to establish the historical base. After
that, the regular live scheduler (D02's `scheduler.py`, already specified) takes over
for incremental growth — see §5.5. Re-run the backfill only if a new instrument is
added or a gap is discovered by the integrity check in §8.

### 5.4 1-minute data: explicitly out of scope for long-term archive
1m data isn't backfilled by default. yfinance's 7-day window means even after a
backfill, the data goes stale fast, and 1m history at real depth (years) generally
requires a paid tick-level provider. Default behavior: keep a rolling ~14-day window of
1m data (useful for very-short-term scalping checks) and don't promise multi-year 1m
archive unless a paid source is explicitly added later. State this limitation in
`config/instruments.yaml` rather than letting it be discovered as a surprise.

### 5.5 Incremental growth after backfill
Once the historical base exists, D02's scheduler fetches new bars daily (or per
candle-close) via yfinance as normal, well within its 60-day window since it's always
querying recent data. The store simply accumulates forward from the backfilled base —
no special logic needed; this is the same append path every other timeframe already uses.

---

## 6. Deriving 4h from 1h (resampling, not fetching)

4h isn't a native yfinance interval. Rather than finding a separate source for it,
derive it from the already-stored 1h data:

```python
def resample_4h(df_1h: pd.DataFrame) -> pd.DataFrame:
    # Resample on UTC boundaries: 00:00, 04:00, 08:00, 12:00, 16:00, 20:00
    # Must NOT bridge the weekend gap into a fabricated candle — forex markets
    # close Friday ~22:00 UTC and reopen Sunday ~22:00 UTC. A naive resample
    # across that gap produces a 4h bar with a multi-day-wide "high/low" that
    # never actually traded. Drop or flag any resampled bar whose underlying
    # 1h bar count is below the expected 4 (i.e. partial bars at session edges).
    ...
```

This is computed once per closed 4h period and cached to its own partition
(`{instrument}/4h/YYYY-MM.parquet`) rather than recomputed on every read — D04's
confluence engine and D08's replay both need 4h data on a hot path, and resampling
2 years of 1h data on every query is wasted work. Cache invalidation is simple here:
since 1h data for closed periods is immutable (§4), the derived 4h cache for those
same closed periods never needs to be recomputed either.

---

## 7. Write reliability: atomic writes

Parquet has no built-in transaction safety — a process killed mid-write corrupts the
file, with no journal to recover from. The fix is a standard pattern, not a new one:

```python
def write_month(df: pd.DataFrame, path: Path) -> None:
    tmp_path = path.with_suffix(".parquet.tmp")
    df.to_parquet(tmp_path)
    tmp_path.rename(path)   # atomic on the same filesystem
```

Write to a temp file, then atomically rename over the real target only on success. If
the process dies during the `to_parquet` call, the `.tmp` file is simply incomplete and
orphaned — the real file is untouched. A crash during a live candle-close write can
never corrupt a month of historical data with this pattern. This is a one-line addition
to `store.py`'s existing write path.

---

## 8. Data integrity: ingest-time and periodic

**Ingest-time** (already specified in D02-DATA.md's `validation.py`): NaN checks,
monotonic timestamp checks, OHLC consistency (`low <= open,close <= high`). This catches
bad data on the way in.

**Periodic re-validation** (new — belongs in D11, not D02): a weekly, low-cost pass over
*already-stored* files, not just incoming data. The failure mode this catches is
different: silent corruption, a partial write that somehow evaded the atomic-write
protection, or a gap that nobody noticed because nothing was actively querying that
range. Concretely:

```python
# src/ops/probes/data_probe.py — extend existing freshness check
def verify_stored_integrity(instrument, timeframe, month) -> IntegrityResult:
    df = store.read_month(instrument, timeframe, month)
    expected_bars = expected_bar_count(timeframe, month, session_hours)
    actual_bars = len(df)
    gap_pct = 1 - (actual_bars / expected_bars)
    # Flag DEGRADED if gap_pct exceeds a threshold (default 5%, configurable —
    # forex holidays and low-liquidity periods cause some legitimate gaps,
    # don't alert on every Christmas week)
```

`expected_bar_count` needs session-hours awareness (already a concept in D11's
`data_probe.py` per D11-OPS.md) — a month's expected 1h bar count isn't simply
`days_in_month * 24`, it has to account for the weekly forex close.

---

## 9. Backup & disaster recovery

The live store (`data/raw/`) is not its own backup. A nightly sync to a second location
(cloud bucket or external volume) matters more for this data than for the codebase,
because the codebase lives in git and is trivially recoverable — the backfilled 5m/15m
history is not. If it's lost, the only way back is re-running the backfill job against
whatever window OANDA/Dukascopy still has available at that point, which may be
materially less than what was originally captured.

Minimum viable backup: a daily `rsync` or cloud-sync of `data/raw/` and
`data/models/registry.json`, retained for at least 30 days of history (so a corruption
discovered late by §8's integrity check still has a clean version to restore from).

---

## 10. Capacity estimate (for planning, not a hard spec)

Rough order-of-magnitude, 4 instruments, 2 years, Parquet-compressed:

| Timeframe | Bars/instrument/year (approx.) | 2yr, 4 instruments | Approx. compressed size |
|---|---|---|---|
| 1m (rolling 14d only) | n/a — not archived | n/a | a few MB, rolling |
| 5m | ~75,000 | ~600,000 | low tens of MB |
| 15m | ~25,000 | ~200,000 | single-digit MB |
| 30m | ~12,500 | ~100,000 | a few MB |
| 1h | ~6,250 | ~50,000 | under 5 MB |
| 4h (derived) | ~1,560 | ~12,500 | under 1 MB |
| 1d, 1w | trivial | trivial | under 1 MB |

**Total: well under 200MB for the entire 2-year, 4-instrument, all-timeframe archive.**
This confirms §1's point — there's no need for distributed storage, chunked uploads, or
any "big data" tooling here. A laptop's free disk space is not a constraint; the only
real constraint was always source retention, which §5's backfill solves once.

---

## 11. Module mapping (where this lives in D02)

No new modules beyond what D02-DATA.md already specifies — this doc fills in the
design behind existing files:

```
src/data/
  store.py              <- add atomic write (§7), monthly partition read/write
  loaders/
    live_data.py          <- yfinance: 1h/1d/1w direct, 5m/15m/30m/1m incremental-only
    oanda_historical.py    <- NEW: backfill source, read-only historical pull (distinct
                               from D06's oanda.py live broker — this just reads candles)
  resample.py               <- NEW: 4h derivation from 1h (§6), session-gap-aware

scripts/
  backfill_historical.py      <- NEW: one-time backfill job (§5.2)

src/ops/probes/
  data_probe.py                 <- extend with verify_stored_integrity() (§8)
```

---

## 12. Testing strategy

Coverage target: 60% (matches D02's existing target; this is an extension of D02's scope).

- Atomic write: simulate a crash mid-write (kill the process or raise mid-`to_parquet`)
  — confirm the real file is untouched and only an orphaned `.tmp` exists
- Backfill idempotency: run the backfill job twice over the same range — confirm no
  duplicate rows and the second run completes near-instantly (skip logic working)
- Backfill resumability: kill the job partway through a multi-month range, re-run,
  confirm it resumes rather than re-fetching completed months
- Resample correctness: known 1h fixture spanning a weekend close — confirm no 4h bar
  is fabricated across the gap, and confirm aligned 4h boundaries (00:00, 04:00, etc.)
- Integrity probe: fixture month with a deliberately deleted chunk of rows — confirm
  `verify_stored_integrity` flags it; fixture with a legitimate holiday gap — confirm
  it does NOT flag (session-hours awareness working)

---

## 13. Implementation phases

Fits inside MASTER.md's existing Phase 1 (D01 + D02), extending the phases already
defined in D02-DATA.md:

### Phase 1 (alongside D02's core build)
1. Add atomic write pattern to `store.py` (§7) — small, do this before any other
   storage code is written, since every later write path depends on it
2. Implement monthly partition read/write per §4

### Phase 1c (D02-DATA.md already has this slot for FRED/macro — extend it)
3. Write `oanda_historical.py` — read-only historical candle pull
4. Write `scripts/backfill_historical.py` — idempotent, resumable, rate-limit aware
5. Run the backfill once for 5m/15m/30m across all 4 initial instruments
6. Write `resample.py` — 4h derivation, session-gap-aware
7. Milestone: 2 years of 5m/15m/30m/1h/4h/1d/1w available in the store for all 4
   instruments, ready for D08's backtest/replay milestone in Phase 2

### Phase 7 (alongside D11's build)
8. Add `verify_stored_integrity()` to `data_probe.py` (§8), weekly schedule
9. Set up backup sync per §9

---

## 14. Known risks & gotchas

- **The backfill window keeps shrinking.** Every day that passes without running the
  5m/15m/30m backfill is 60 days of yfinance-reachable history permanently gone (it
  can't be recovered later from yfinance, only from a paid source at that point). If
  this hasn't been run yet, treat it as time-sensitive, not just "do it eventually."
- **OANDA practice account history depth isn't unlimited either** — verify the actual
  available window before assuming the backfill can reach the full 2 years; if it can't,
  Dukascopy's export is the fallback for whatever gap remains.
- **Resample correctness around weekend gaps is the single easiest place to introduce
  silently wrong data** — a fabricated 4h candle spanning Friday close to Sunday open
  would have absurd high/low values that no indicator would catch as obviously wrong,
  it would just quietly corrupt every downstream signal computed from it. This is why
  §6 calls it out specifically and why it needs its own dedicated test.
- **Don't let the integrity probe (§8) become noisy.** Forex has legitimate gaps around
  holidays and low-liquidity periods; an over-sensitive threshold trains you to ignore
  the alert, which defeats its purpose — same alert-fatigue risk D11-OPS.md already
  flags for its other probes.
