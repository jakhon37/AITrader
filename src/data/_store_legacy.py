"""D02-DATA — DataStore: unified Parquet + SQLite data access layer.

Responsibilities
----------------
- Write and query OHLCV data using Parquet, partitioned by
  {instrument}/{timeframe}/YYYY-MM.parquet
- Write and query news articles (SQLite, Phase 1b)
- Write and query economic calendar events (SQLite, Phase 1b)

Public API
----------
    store = DataStore(base_dir="data")

    # OHLCV
    store.write_ohlcv(instrument, timeframe, df)
    df = store.get_ohlcv(instrument, timeframe, start, end)

    # News (Phase 1b — stubs raise NotImplementedError until news_fetcher ships)
    store.write_news(articles)
    articles = store.get_news(instrument, start, end)

    # Calendar (Phase 1b)
    store.write_calendar_events(events)
    events = store.get_economic_events(start, end, impact_filter)

Design rules
------------
- Fail loud: a missing or malformed Parquet raises DataError, never returns empty
  silently.  Callers that genuinely expect "no data yet" may catch DataError.
- All timestamps are UTC (timezone-aware).  tz-naive inputs are rejected.
- Parquet append: monthly partitioning, append-only within the current month.
  Duplicate rows (same timestamp) are dropped on read (last-write wins).
- Thread safety: Parquet reads are safe concurrently; writes are NOT locked here —
  only one writer (scheduler.py) should call write_ohlcv at a time.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

from src.core.contracts import Instrument, Timeframe
from src.core.exceptions import DataError
from src.core.logging import get_logger
from src.data.models import NewsArticle, RawCalendarEvent

_log = get_logger("D02-DATA")

# ── Parquet helpers ───────────────────────────────────────────────────────────

def _parquet_path(base_dir: Path, instrument: Instrument, timeframe: Timeframe, dt: datetime) -> Path:
    """Return the monthly Parquet file path for a given instrument/timeframe/month."""
    month_key = dt.strftime("%Y-%m")
    return base_dir / "raw" / instrument.value / timeframe.value / f"{month_key}.parquet"


def _ensure_utc(ts: pd.Series) -> pd.Series:  # noqa: UP007
    """Ensure a datetime Series is UTC-aware; raise DataError if tz-naive."""
    if ts.dt.tz is None:
        raise DataError(
            "Timestamps must be timezone-aware UTC. "
            "Localize with df.index = df.index.tz_localize('UTC') before storing."
        )
    return ts.dt.tz_convert("UTC")


# ── DataStore ─────────────────────────────────────────────────────────────────

class DataStore:
    """Unified data access layer for D02-DATA.

    Parameters
    ----------
    base_dir:
        Root of the data directory tree. Defaults to ``data/`` relative to cwd.
        Parquet files land in ``{base_dir}/raw/{instrument}/{timeframe}/YYYY-MM.parquet``.
        SQLite databases land in ``{base_dir}/news.db`` and ``{base_dir}/calendar.db``.
    """

    def __init__(self, base_dir: str | Path = "data") -> None:
        self._base = Path(base_dir)
        self._base.mkdir(parents=True, exist_ok=True)
        self._news_db_path = self._base / "news.db"
        self._calendar_db_path = self._base / "calendar.db"
        self._init_news_schema()
        self._init_calendar_schema()

    @property
    def base_dir(self) -> Path:
        """Return the root path of the data directory tree."""
        return self._base

    # ── OHLCV ─────────────────────────────────────────────────────────────────

    def write_ohlcv(
        self,
        instrument: Instrument,
        timeframe: Timeframe,
        df: pd.DataFrame,
    ) -> None:
        """Append validated OHLCV rows to the monthly Parquet partition.

        Parameters
        ----------
        instrument:
            The instrument enum (e.g. Instrument.EURUSD).
        timeframe:
            The timeframe enum (e.g. Timeframe.H1).
        df:
            DataFrame with a timezone-aware UTC DatetimeIndex and columns:
            open, high, low, close, volume (volume may be 0 for Forex).

        Raises
        ------
        DataError
            If the DataFrame is empty, has tz-naive index, or is missing columns.
        """
        if df.empty:
            raise DataError(f"write_ohlcv: empty DataFrame for {instrument.value}/{timeframe.value}")

        if not isinstance(df.index, pd.DatetimeIndex):
            raise DataError("write_ohlcv: DataFrame index must be a DatetimeIndex.")

        if df.index.tz is None:
            raise DataError(
                "write_ohlcv: DatetimeIndex must be timezone-aware (UTC). "
                "Use df.index = df.index.tz_localize('UTC')."
            )

        required = {"open", "high", "low", "close"}
        missing = required - set(df.columns)
        if missing:
            raise DataError(f"write_ohlcv: missing columns {sorted(missing)}")

        # Group by month and write/append per partition
        df = df.copy()
        df.index = df.index.tz_convert("UTC")

        # Add volume column if absent (0.0 for Forex pairs that don't report volume)
        if "volume" not in df.columns:
            df["volume"] = 0.0

        months = df.groupby(df.index.to_period("M"))
        for period, chunk in months:
            # Use the first timestamp of the chunk to build the path
            sample_dt = chunk.index[0].to_pydatetime()
            path = _parquet_path(self._base, instrument, timeframe, sample_dt)
            path.parent.mkdir(parents=True, exist_ok=True)

            tmp_path = path.with_suffix(".parquet.tmp")
            try:
                if path.exists():
                    existing = pd.read_parquet(path)
                    existing.index = pd.to_datetime(existing.index, utc=True)
                    combined = pd.concat([existing, chunk[["open", "high", "low", "close", "volume"]]])
                    # Drop duplicates keeping the latest write (last wins)
                    combined = combined[~combined.index.duplicated(keep="last")]
                    combined.sort_index(inplace=True)
                    combined.to_parquet(tmp_path)
                else:
                    chunk[["open", "high", "low", "close", "volume"]].to_parquet(tmp_path)
                
                # Atomic rename on the same filesystem
                tmp_path.rename(path)
            except Exception as e:
                if tmp_path.exists():
                    try:
                        tmp_path.unlink()
                    except Exception:
                        pass
                raise e

            _log.debug(
                "ohlcv_written",
                instrument=instrument.value,
                timeframe=timeframe.value,
                rows=len(chunk),
                path=str(path),
            )

    def get_ohlcv(
        self,
        instrument: Instrument,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        """Query OHLCV bars in the [start, end] range (inclusive).

        Parameters
        ----------
        instrument, timeframe:
            Which partition to read.
        start, end:
            UTC-aware datetimes. Both are required.

        Returns
        -------
        pd.DataFrame
            Indexed by UTC datetime, columns: open, high, low, close, volume.
            Sorted ascending by timestamp.

        Raises
        ------
        DataError
            If start/end are tz-naive, or if no Parquet files exist for the
            requested range.
        """
        if start.tzinfo is None or end.tzinfo is None:
            raise DataError("get_ohlcv: start and end must be timezone-aware UTC datetimes.")
        if start > end:
            raise DataError(f"get_ohlcv: start ({start}) is after end ({end}).")

        start = start.astimezone(timezone.utc)
        end = end.astimezone(timezone.utc)

        # Collect all monthly Parquet files that overlap the requested range
        parquet_root = self._base / "raw" / instrument.value / timeframe.value
        if not parquet_root.exists():
            raise DataError(
                f"No data for {instrument.value}/{timeframe.value}. "
                f"Expected directory: {parquet_root}. "
                "Run download_sample_data.py or write OHLCV first."
            )

        files = sorted(parquet_root.glob("*.parquet"))
        if not files:
            raise DataError(
                f"No Parquet files found in {parquet_root} for "
                f"{instrument.value}/{timeframe.value}."
            )

        # Filter to months that overlap [start, end]
        relevant: list[Path] = []
        for f in files:
            stem = f.stem  # "YYYY-MM"
            try:
                file_period = pd.Period(stem, freq="M")
            except Exception:
                continue
            file_start = file_period.start_time.tz_localize("UTC")
            file_end = file_period.end_time.tz_localize("UTC")
            if file_start <= end and file_end >= start:
                relevant.append(f)

        if not relevant:
            raise DataError(
                f"No OHLCV data found for {instrument.value}/{timeframe.value} "
                f"between {start.date()} and {end.date()}."
            )

        chunks = []
        for f in relevant:
            try:
                chunk = pd.read_parquet(f)
                chunk.index = pd.to_datetime(chunk.index, utc=True)
                chunks.append(chunk)
            except Exception as exc:
                raise DataError(f"Failed to read Parquet {f}: {exc}") from exc

        df = pd.concat(chunks)
        df = df[~df.index.duplicated(keep="last")]
        df.sort_index(inplace=True)

        # Slice to requested range
        df = df.loc[start:end]

        if df.empty:
            raise DataError(
                f"OHLCV query returned empty result for {instrument.value}/{timeframe.value} "
                f"[{start.date()} → {end.date()}]. Data exists but not in this range."
            )

        _log.debug(
            "ohlcv_queried",
            instrument=instrument.value,
            timeframe=timeframe.value,
            rows=len(df),
            start=str(start.date()),
            end=str(end.date()),
        )
        return df

    def list_ohlcv_range(
        self,
        instrument: Instrument,
        timeframe: Timeframe,
    ) -> tuple[Optional[datetime], Optional[datetime]]:
        """Return the (earliest, latest) timestamps available, or (None, None) if no data."""
        parquet_root = self._base / "raw" / instrument.value / timeframe.value
        if not parquet_root.exists():
            return None, None
        files = sorted(parquet_root.glob("*.parquet"))
        if not files:
            return None, None

        first_ts: Optional[datetime] = None
        last_ts: Optional[datetime] = None
        for f in files:
            try:
                chunk = pd.read_parquet(f)
                chunk.index = pd.to_datetime(chunk.index, utc=True)
                if not chunk.empty:
                    if first_ts is None or chunk.index[0] < first_ts:
                        first_ts = chunk.index[0].to_pydatetime()
                    if last_ts is None or chunk.index[-1] > last_ts:
                        last_ts = chunk.index[-1].to_pydatetime()
            except Exception:
                continue
        return first_ts, last_ts

    # ── News ──────────────────────────────────────────────────────────────────

    def _init_news_schema(self) -> None:
        """Create news SQLite table if it does not yet exist."""
        with sqlite3.connect(self._news_db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS articles (
                    article_id   TEXT PRIMARY KEY,
                    headline     TEXT NOT NULL,
                    url          TEXT,
                    source       TEXT NOT NULL DEFAULT 'unknown',
                    published_at TEXT NOT NULL,   -- UTC ISO-8601
                    instruments  TEXT NOT NULL DEFAULT '[]', -- JSON list of strings
                    body_snippet TEXT,
                    fetched_at   TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_articles_published "
                "ON articles (published_at)"
            )

    def write_news(self, articles: list[NewsArticle]) -> None:
        """Upsert news articles into SQLite.

        Duplicate article_id rows are silently ignored (INSERT OR IGNORE).
        """
        if not articles:
            return
        rows = [
            (
                a.article_id,
                a.headline,
                a.url,
                a.source,
                a.published_at.isoformat(),
                json.dumps(a.instruments),
                a.body_snippet,
                a.fetched_at.isoformat(),
            )
            for a in articles
        ]
        with sqlite3.connect(self._news_db_path) as conn:
            conn.executemany(
                """
                INSERT OR IGNORE INTO articles
                    (article_id, headline, url, source, published_at,
                     instruments, body_snippet, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
        _log.debug("news_written", count=len(rows))

    def get_news(
        self,
        instrument: Optional[Instrument],
        start: datetime,
        end: datetime,
    ) -> list[NewsArticle]:
        """Query news articles in [start, end].

        Parameters
        ----------
        instrument:
            If provided, filter to articles that mention this instrument.
            If None, return all articles in the time range.
        start, end:
            UTC-aware datetimes.

        Returns
        -------
        list[NewsArticle] sorted ascending by published_at.

        Raises
        ------
        DataError
            If start/end are tz-naive.
        """
        if start.tzinfo is None or end.tzinfo is None:
            raise DataError("get_news: start and end must be UTC-aware datetimes.")

        start_iso = start.astimezone(timezone.utc).isoformat()
        end_iso = end.astimezone(timezone.utc).isoformat()

        with sqlite3.connect(self._news_db_path) as conn:
            rows = conn.execute(
                """
                SELECT article_id, headline, url, source, published_at,
                       instruments, body_snippet, fetched_at
                FROM articles
                WHERE published_at >= ? AND published_at <= ?
                ORDER BY published_at ASC
                """,
                (start_iso, end_iso),
            ).fetchall()

        articles: list[NewsArticle] = []
        for row in rows:
            art = NewsArticle(
                article_id=row[0],
                headline=row[1],
                url=row[2],
                source=row[3],
                published_at=datetime.fromisoformat(row[4]),
                instruments=json.loads(row[5] or "[]"),
                body_snippet=row[6],
                fetched_at=datetime.fromisoformat(row[7]),
            )
            if instrument is None or instrument.value in art.instruments:
                articles.append(art)

        _log.debug(
            "news_queried",
            instrument=instrument.value if instrument else "all",
            start=start.date().isoformat(),
            end=end.date().isoformat(),
            count=len(articles),
        )
        return articles

    # ── Calendar ──────────────────────────────────────────────────────────────

    def _init_calendar_schema(self) -> None:
        """Create calendar SQLite table if it does not yet exist."""
        with sqlite3.connect(self._calendar_db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS calendar (
                    event_id                  TEXT PRIMARY KEY,
                    name                      TEXT NOT NULL,
                    timestamp                 TEXT NOT NULL,  -- UTC ISO-8601
                    impact                    TEXT NOT NULL,  -- low/medium/high
                    instruments               TEXT NOT NULL DEFAULT '[]', -- JSON
                    actual                    REAL,
                    forecast                  REAL,
                    previous                  REAL,
                    surprise_pct              REAL,
                    fetched_at                TEXT NOT NULL,
                    pre_release_notified      INTEGER NOT NULL DEFAULT 0,
                    post_release_notified     INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_calendar_timestamp "
                "ON calendar (timestamp)"
            )

    def write_calendar_events(self, events: list[RawCalendarEvent]) -> None:
        """Upsert calendar events. Existing rows are updated (INSERT OR REPLACE)."""
        if not events:
            return
        rows = [
            (
                e.event_id,
                e.name,
                e.timestamp.isoformat(),
                e.impact,
                json.dumps(e.instruments),
                e.actual,
                e.forecast,
                e.previous,
                e.surprise_pct,
                e.fetched_at.isoformat(),
                int(e.pre_release_notified),
                int(e.post_release_notified),
            )
            for e in events
        ]
        with sqlite3.connect(self._calendar_db_path) as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO calendar
                    (event_id, name, timestamp, impact, instruments,
                     actual, forecast, previous, surprise_pct, fetched_at,
                     pre_release_notified, post_release_notified)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
        _log.debug("calendar_written", count=len(rows))

    def get_economic_events(
        self,
        start: datetime,
        end: datetime,
        impact_filter: Optional[str] = None,
    ) -> list[RawCalendarEvent]:
        """Query calendar events in [start, end].

        Parameters
        ----------
        start, end:
            UTC-aware datetimes (event timestamp range).
        impact_filter:
            If provided, one of "low", "medium", "high" — filters to this
            impact level.  If None, all impact levels are returned.

        Returns
        -------
        list[RawCalendarEvent] sorted ascending by timestamp.

        Raises
        ------
        DataError
            If start/end are tz-naive or impact_filter is not a valid level.
        """
        if start.tzinfo is None or end.tzinfo is None:
            raise DataError("get_economic_events: start and end must be UTC-aware.")
        if impact_filter is not None and impact_filter not in ("low", "medium", "high"):
            raise DataError(
                f"get_economic_events: invalid impact_filter {impact_filter!r}. "
                "Must be 'low', 'medium', 'high', or None."
            )

        start_iso = start.astimezone(timezone.utc).isoformat()
        end_iso = end.astimezone(timezone.utc).isoformat()

        query = (
            "SELECT event_id, name, timestamp, impact, instruments, "
            "actual, forecast, previous, surprise_pct, fetched_at, "
            "pre_release_notified, post_release_notified "
            "FROM calendar "
            "WHERE timestamp >= ? AND timestamp <= ? "
        )
        params: list = [start_iso, end_iso]

        if impact_filter:
            query += "AND impact = ? "
            params.append(impact_filter)

        query += "ORDER BY timestamp ASC"

        with sqlite3.connect(self._calendar_db_path) as conn:
            rows = conn.execute(query, params).fetchall()

        events: list[RawCalendarEvent] = []
        for row in rows:
            events.append(
                RawCalendarEvent(
                    event_id=row[0],
                    name=row[1],
                    timestamp=datetime.fromisoformat(row[2]),
                    impact=row[3],  # type: ignore[arg-type]
                    instruments=json.loads(row[4] or "[]"),
                    actual=row[5],
                    forecast=row[6],
                    previous=row[7],
                    surprise_pct=row[8],
                    fetched_at=datetime.fromisoformat(row[9]),
                    pre_release_notified=bool(row[10]),
                    post_release_notified=bool(row[11]),
                )
            )

        _log.debug(
            "calendar_queried",
            start=start.date().isoformat(),
            end=end.date().isoformat(),
            impact=impact_filter or "all",
            count=len(events),
        )
        return events

    def mark_event_notified(
        self,
        event_id: str,
        *,
        pre: bool = False,
        post: bool = False,
    ) -> None:
        """Mark a calendar event as having sent its pre- or post-release notification."""
        if pre:
            col = "pre_release_notified"
        elif post:
            col = "post_release_notified"
        else:
            return
        with sqlite3.connect(self._calendar_db_path) as conn:
            conn.execute(
                f"UPDATE calendar SET {col} = 1 WHERE event_id = ?",  # noqa: S608
                (event_id,),
            )
