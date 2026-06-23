"""D02-DATA — FredFetcher: FRED macro data ingestion.

Fetches the following series from the St. Louis Fed FRED API:
  DFF      — Effective Federal Funds Rate (daily)
  CPIAUCSL — Consumer Price Index (monthly)
  UNRATE   — Unemployment Rate (monthly)
  T10Y2Y   — 10-Year minus 2-Year Treasury Spread (daily, yield curve)

Behaviour:
  - Runs once per week (Sunday UTC 00:00) by default.
  - Stores series data in DataStore SQLite (fred.db).
  - Exposes get_fred_series() for D03/D05 to query the latest value.
  - Fail loud: API errors raise DataError.
  - All dates normalized to UTC midnight.

Usage:
    fetcher = FredFetcher(store, clock, api_key=os.getenv("FRED_API_KEY"))
    await fetcher.run()     # blocks; run as asyncio.Task
    fetcher.stop()

    # One-shot update:
    await fetcher.fetch_all()

Requirements:
    httpx (in [live_data] extras)
"""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from src.core.clock import VirtualClock
from src.core.exceptions import DataError
from src.core.logging import get_logger

_log = get_logger("D02-DATA.fred")

# ── Series config ─────────────────────────────────────────────────────────────

_FRED_SERIES: dict[str, str] = {
    "DFF":      "Effective Federal Funds Rate",
    "CPIAUCSL": "Consumer Price Index (All Urban, SA)",
    "UNRATE":   "Unemployment Rate",
    "T10Y2Y":   "10Y-2Y Treasury Yield Spread",
}

_FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

# ── FredFetcher ───────────────────────────────────────────────────────────────

class FredFetcher:
    """Fetches FRED macro series and stores them in SQLite.

    Parameters
    ----------
    data_base_dir:
        Root of the data directory (same as DataStore.base_dir).
        FRED data is stored at ``{data_base_dir}/fred.db``.
    clock:
        VirtualClock — always use clock.now() for current time.
    api_key:
        FRED API key (free at fred.stlouisfed.org). If None, fetches are skipped
        with a warning.
    poll_interval_seconds:
        How often to refresh. Default 604800 = 7 days (weekly).
    lookback_years:
        How many years of history to fetch on first run (default 5).
    """

    def __init__(
        self,
        data_base_dir: str | Path,
        clock: VirtualClock,
        api_key: Optional[str] = None,
        poll_interval_seconds: int = 604_800,
        lookback_years: int = 5,
    ) -> None:
        self._base = Path(data_base_dir)
        self._clock = clock
        self._api_key = api_key
        self._poll_interval = poll_interval_seconds
        self._lookback_years = lookback_years
        self._db_path = self._base / "fred.db"
        self._running = False

        self._ensure_schema()

    # ── Schema ────────────────────────────────────────────────────────────────

    def _ensure_schema(self) -> None:
        """Create the SQLite table if it doesn't exist."""
        self._base.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS fred_observations (
                    series_id   TEXT NOT NULL,
                    date        TEXT NOT NULL,       -- ISO date string, UTC midnight
                    value       REAL,                -- NULL means 'missing' / '.'
                    fetched_at  TEXT NOT NULL,
                    PRIMARY KEY (series_id, date)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_fred_series_date "
                "ON fred_observations (series_id, date)"
            )

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def run(self) -> None:
        """Weekly fetch loop — blocks until stop() is called."""
        self._running = True
        _log.info("fred_fetcher_started", poll_interval_days=self._poll_interval // 86400)
        while self._running:
            await self.fetch_all()
            await asyncio.sleep(self._poll_interval)

    def stop(self) -> None:
        self._running = False
        _log.info("fred_fetcher_stopping")

    # ── Fetch ─────────────────────────────────────────────────────────────────

    async def fetch_all(self) -> None:
        """Fetch all configured series and store in SQLite."""
        if not self._api_key:
            _log.warning("fred_api_key_missing", action="skipping_fetch")
            return

        now = self._clock.now()
        start_date = (now - timedelta(days=365 * self._lookback_years)).strftime("%Y-%m-%d")
        end_date = now.strftime("%Y-%m-%d")

        tasks = [
            self._fetch_series(series_id, start_date, end_date)
            for series_id in _FRED_SERIES
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for series_id, result in zip(_FRED_SERIES, results):
            if isinstance(result, Exception):
                _log.error("fred_series_failed", series=series_id, error=str(result))
            else:
                _log.info("fred_series_stored", series=series_id, rows=result)

    async def _fetch_series(
        self,
        series_id: str,
        observation_start: str,
        observation_end: str,
    ) -> int:
        """Fetch a single FRED series and upsert into SQLite. Returns row count."""
        try:
            import httpx
        except ImportError as e:
            raise DataError("httpx not installed") from e

        params = {
            "series_id": series_id,
            "observation_start": observation_start,
            "observation_end": observation_end,
            "api_key": self._api_key,
            "file_type": "json",
            "sort_order": "asc",
        }

        for attempt in range(5):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.get(_FRED_BASE, params=params)
                if resp.status_code == 429:
                    wait = int(resp.headers.get("Retry-After", 60))
                    await asyncio.sleep(wait)
                    continue
                resp.raise_for_status()
                data = resp.json()
                break
            except Exception as exc:
                if attempt == 4:
                    raise DataError(
                        f"FRED API failed for {series_id} after 5 attempts: {exc}"
                    ) from exc
                await asyncio.sleep(2 ** attempt)

        observations = data.get("observations", [])
        if not observations:
            return 0

        now_iso = self._clock.now().isoformat()
        rows = []
        for obs in observations:
            date_str = obs.get("date", "")
            raw_value = obs.get("value", ".")
            try:
                value: Optional[float] = None if raw_value in (".", "") else float(raw_value)
            except ValueError:
                value = None
            rows.append((series_id, date_str, value, now_iso))

        with sqlite3.connect(self._db_path) as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO fred_observations (series_id, date, value, fetched_at)
                VALUES (?, ?, ?, ?)
                """,
                rows,
            )

        _log.debug(
            "fred_upserted",
            series=series_id,
            rows=len(rows),
            start=observation_start,
            end=observation_end,
        )
        return len(rows)

    # ── Query API ─────────────────────────────────────────────────────────────

    def get_latest(self, series_id: str) -> Optional[tuple[datetime, float]]:
        """Return the latest (date, value) for a series, or None if no data.

        Parameters
        ----------
        series_id:
            One of: "DFF", "CPIAUCSL", "UNRATE", "T10Y2Y".

        Returns
        -------
        (date, value) tuple or None.
        """
        if series_id not in _FRED_SERIES:
            raise DataError(f"Unknown FRED series: {series_id!r}. Known: {list(_FRED_SERIES)}")

        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                """
                SELECT date, value FROM fred_observations
                WHERE series_id = ? AND value IS NOT NULL
                ORDER BY date DESC
                LIMIT 1
                """,
                (series_id,),
            ).fetchone()

        if not row:
            return None

        date_str, value = row
        dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return dt, float(value)

    def get_series(
        self,
        series_id: str,
        start: datetime,
        end: datetime,
    ) -> list[tuple[datetime, float]]:
        """Return all (date, value) observations in [start, end].

        Parameters
        ----------
        series_id:
            Series identifier.
        start, end:
            UTC-aware datetimes. Comparison is date-level (time portion ignored).

        Returns
        -------
        List of (date, value) tuples, sorted ascending.
        """
        if series_id not in _FRED_SERIES:
            raise DataError(f"Unknown FRED series: {series_id!r}")

        start_str = start.strftime("%Y-%m-%d")
        end_str = end.strftime("%Y-%m-%d")

        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                """
                SELECT date, value FROM fred_observations
                WHERE series_id = ? AND date >= ? AND date <= ? AND value IS NOT NULL
                ORDER BY date ASC
                """,
                (series_id, start_str, end_str),
            ).fetchall()

        return [
            (datetime.strptime(r[0], "%Y-%m-%d").replace(tzinfo=timezone.utc), float(r[1]))
            for r in rows
        ]

    @staticmethod
    def available_series() -> dict[str, str]:
        """Return the mapping of series_id → description."""
        return dict(_FRED_SERIES)
