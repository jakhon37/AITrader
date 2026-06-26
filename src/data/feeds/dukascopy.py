"""D02-DATA — Dukascopy HTTP feed (M1 binary .bi5 daily files)."""

from __future__ import annotations

import lzma
import random
import struct
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd
import requests

from src.core.candle import candle_open_time
from src.core.contracts import Instrument, OHLCVBar, Timeframe
from src.core.exceptions import DataError
from src.core.ids import new_signal_id
from src.core.logging import get_logger
from src.data.feeds.base import OHLCVFeed
from src.data.feeds.dukascopy_ticks import fetch_today_m1_from_ticks, parse_tick_hour
from src.data.feeds.lock import DUKASCOPY_LOCK, dukascopy_lock_held

_log = get_logger("D02-DATA")

_SYMBOL_MAP: dict[Instrument, str] = {
    Instrument.EURUSD: "EURUSD",
    Instrument.GBPUSD: "GBPUSD",
    Instrument.USDJPY: "USDJPY",
    Instrument.XAUUSD: "XAUUSD",
}

_DIVISORS: dict[str, float] = {
    "EURUSD": 100_000.0,
    "GBPUSD": 100_000.0,
    "USDJPY": 1_000.0,
    "XAUUSD": 1_000.0,
}

_TF_RESAMPLE: dict[Timeframe, str] = {
    Timeframe.M5: "5min",
    Timeframe.M15: "15min",
    Timeframe.M30: "30min",
    Timeframe.H1: "1h",
    Timeframe.H4: "4h",
    Timeframe.D1: "1d",
    Timeframe.W1: "1wk",
}

_RECORD_FMT = ">5If"
_RECORD_SIZE = struct.calcsize(_RECORD_FMT)


def _resample_m1(df: pd.DataFrame, timeframe: Timeframe) -> pd.DataFrame:
    rule = _TF_RESAMPLE.get(timeframe)
    if rule is None:
        return df
    resampled = pd.DataFrame()
    resampled["open"] = df["open"].resample(rule, closed="left", label="left").first()
    resampled["high"] = df["high"].resample(rule, closed="left", label="left").max()
    resampled["low"] = df["low"].resample(rule, closed="left", label="left").min()
    resampled["close"] = df["close"].resample(rule, closed="left", label="left").last()
    resampled["volume"] = df["volume"].resample(rule, closed="left", label="left").sum()
    return resampled.dropna()


@dataclass
class _M1CacheEntry:
    df: pd.DataFrame
    fetched_at: float


def bars_from_m1_df(
    instrument: Instrument,
    timeframe: Timeframe,
    m1_df: pd.DataFrame,
    *,
    now: Optional[datetime] = None,
) -> tuple[OHLCVBar, Optional[OHLCVBar]]:
    """Derive completed/active bars for any timeframe from a shared M1 window."""
    if m1_df.empty:
        raise DataError(f"No M1 rows to derive {timeframe.value} for {instrument.value}")

    now = now or datetime.now(timezone.utc)
    candle_open = candle_open_time(now, timeframe)
    df = m1_df if timeframe == Timeframe.M1 else _resample_m1(m1_df, timeframe)
    if df.empty:
        raise DataError(f"Resample to {timeframe.value} produced no bars for {instrument.value}")

    def _row_to_bar(ts: datetime, row: pd.Series, source: str) -> OHLCVBar:
        return OHLCVBar(
            signal_id=new_signal_id(),
            instrument=instrument,
            timeframe=timeframe,
            timestamp=ts,
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row.get("volume", 0.0) or 0.0),
            source=source,
        )

    active_bar: Optional[OHLCVBar] = None
    completed_bar: Optional[OHLCVBar] = None

    if candle_open in df.index:
        active_bar = _row_to_bar(candle_open, df.loc[candle_open], "dukascopy_active")
        prior = df.loc[: candle_open - timedelta(microseconds=1)]
        if not prior.empty:
            ts = prior.index[-1].to_pydatetime()
            completed_bar = _row_to_bar(ts, prior.iloc[-1], "dukascopy")
    else:
        ts = df.index[-1].to_pydatetime()
        completed_bar = _row_to_bar(ts, df.iloc[-1], "dukascopy")

    if completed_bar is None:
        raise DataError(f"No completed bar for {instrument.value}/{timeframe.value}")
    return completed_bar, active_bar


def _parse_bi5_day(content: bytes, year: int, month: int, day: int, divisor: float) -> pd.DataFrame:
    decompressed = lzma.decompress(content)
    num_records = len(decompressed) // _RECORD_SIZE
    if num_records == 0:
        return pd.DataFrame()

    records = []
    for i in range(num_records):
        offset = i * _RECORD_SIZE
        chunk = decompressed[offset : offset + _RECORD_SIZE]
        records.append(struct.unpack(_RECORD_FMT, chunk))

    day_df = pd.DataFrame(records, columns=["time_sec", "open", "close", "low", "high", "volume"])
    base_dt = datetime(year, month, day, tzinfo=timezone.utc)
    day_df["timestamp"] = base_dt + pd.to_timedelta(day_df["time_sec"], unit="s")

    for col in ["open", "high", "low", "close"]:
        day_df[col] = day_df[col] / divisor

    day_df["high"] = day_df[["open", "close", "low", "high"]].max(axis=1)
    day_df["low"] = day_df[["open", "close", "low", "high"]].min(axis=1)

    return day_df.set_index("timestamp")[["open", "high", "low", "close", "volume"]]


class DukascopyFeed(OHLCVFeed):
    """Fetch M1 candles from Dukascopy datafeed and resample to higher timeframes."""

    def __init__(
        self,
        pacing_sec: float = 0.5,
        cooldown_every: int = 50,
        request_timeout_sec: float = 30.0,
        live_request_timeout_sec: float = 12.0,
        live_m1_cache_ttl_sec: float = 30.0,
        live_m1_lookback_days: int = 2,
        tick_enabled: bool = True,
    ) -> None:
        self._pacing_sec = pacing_sec
        self._cooldown_every = cooldown_every
        self._request_timeout_sec = request_timeout_sec
        self._live_request_timeout_sec = live_request_timeout_sec
        self._live_m1_cache_ttl_sec = live_m1_cache_ttl_sec
        self._live_m1_lookback_days = live_m1_lookback_days
        self._tick_enabled = tick_enabled
        self._requests_count = 0
        self._m1_cache: dict[Instrument, _M1CacheEntry] = {}

    @property
    def source_name(self) -> str:
        return "dukascopy"

    def _symbol(self, instrument: Instrument) -> str:
        symbol = _SYMBOL_MAP.get(instrument)
        if symbol is None:
            raise DataError(f"No Dukascopy mapping for {instrument.value}")
        return symbol

    def _download_day(
        self,
        symbol: str,
        year: int,
        month: int,
        day: int,
        *,
        timeout_sec: Optional[float] = None,
        max_retries: int = 3,
    ) -> Optional[pd.DataFrame]:
        url = (
            f"https://datafeed.dukascopy.com/datafeed/"
            f"{symbol}/{year}/{month - 1:02d}/{day:02d}/BID_candles_min_1.bi5"
        )
        divisor = _DIVISORS.get(symbol, 100_000.0)
        timeout = self._request_timeout_sec if timeout_sec is None else timeout_sec

        res: Optional[requests.Response] = None
        for attempt in range(max_retries):
            try:
                res = requests.get(url, timeout=timeout)
                if res.status_code in (403, 429):
                    backoff = [60, 120, 300][min(attempt, 2)]
                    _log.warning(
                        "dukascopy_rate_limit",
                        date=f"{year}-{month:02d}-{day:02d}",
                        status=res.status_code,
                        backoff_sec=backoff,
                    )
                    time.sleep(backoff)
                    continue
                break
            except Exception as exc:
                if attempt == max_retries - 1:
                    _log.warning(
                        "dukascopy_day_skipped",
                        date=f"{year}-{month:02d}-{day:02d}",
                        url=url,
                        error=str(exc),
                    )
                    return None
                time.sleep(min(5, 2 * (attempt + 1)))

        if res is None:
            return None

        if res.status_code == 404:
            return None
        if res.status_code != 200:
            _log.warning("dukascopy_download_non_200", url=url, status=res.status_code)
            return None

        try:
            return _parse_bi5_day(res.content, year, month, day, divisor)
        except Exception as exc:
            _log.warning("dukascopy_parse_error", url=url, error=str(exc))
            return None

    def _download_hour_ticks(
        self,
        symbol: str,
        year: int,
        month: int,
        day: int,
        hour: int,
        *,
        timeout_sec: Optional[float] = None,
    ) -> Optional[pd.DataFrame]:
        """Download one hour of ticks and return bid/ask/volume rows."""
        url = (
            f"https://datafeed.dukascopy.com/datafeed/"
            f"{symbol}/{year}/{month - 1:02d}/{day:02d}/{hour:02d}h_ticks.bi5"
        )
        divisor = _DIVISORS.get(symbol, 100_000.0)
        timeout = self._request_timeout_sec if timeout_sec is None else timeout_sec
        try:
            res = requests.get(url, timeout=timeout)
        except Exception as exc:
            _log.warning("dukascopy_tick_connection_error", url=url, error=str(exc))
            return None

        if res.status_code == 404:
            return None
        if res.status_code != 200:
            _log.warning("dukascopy_tick_non_200", url=url, status=res.status_code)
            return None

        try:
            return parse_tick_hour(res.content, year, month, day, hour, divisor)
        except Exception as exc:
            _log.warning("dukascopy_tick_parse_error", url=url, error=str(exc))
            return None

    def _fetch_today_m1_from_ticks(
        self,
        symbol: str,
        *,
        live_mode: bool = False,
    ) -> pd.DataFrame:
        """Build today's M1 bars from hourly tick files (current UTC day)."""
        if not self._tick_enabled:
            return pd.DataFrame()

        tick_timeout = (
            self._live_request_timeout_sec if live_mode else self._request_timeout_sec
        )

        def _dl(year: int, month: int, day: int, hour: int) -> Optional[pd.DataFrame]:
            return self._download_hour_ticks(
                symbol, year, month, day, hour, timeout_sec=tick_timeout
            )

        max_hours = 2 if live_mode else None
        m1 = fetch_today_m1_from_ticks(_dl, max_hours=max_hours)
        if not m1.empty:
            _log.info(
                "dukascopy_tick_today_m1",
                rows=len(m1),
                first=str(m1.index[0]),
                last=str(m1.index[-1]),
            )
        return m1

    def _fetch_m1_hybrid(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        *,
        live_mode: bool = False,
    ) -> pd.DataFrame:
        """Daily .bi5 for completed days + hourly ticks for current UTC day."""
        start = start.astimezone(timezone.utc)
        end = end.astimezone(timezone.utc)
        today = datetime.now(timezone.utc).date()
        chunks: list[pd.DataFrame] = []
        day_timeout = self._live_request_timeout_sec if live_mode else None
        day_retries = 2 if live_mode else 3

        current = start.date()
        end_date = end.date()
        if live_mode:
            # Live polls only need recent days — never walk a multi-week gap.
            earliest = max(current, today - timedelta(days=2))
            current = earliest

        while current < today and current <= end_date:
            day_df = self._download_day(
                symbol,
                current.year,
                current.month,
                current.day,
                timeout_sec=day_timeout,
                max_retries=day_retries,
            )
            if day_df is not None and not day_df.empty:
                chunks.append(day_df)
            self._requests_count += 1
            if not live_mode:
                if self._requests_count % self._cooldown_every == 0:
                    time.sleep(10)
                elif current < min(end_date, today - timedelta(days=1)):
                    time.sleep(self._pacing_sec + random.uniform(0.0, 0.2))
            current += timedelta(days=1)

        if end_date >= today:
            # Daily minute candles update through the session; tick hours can 404.
            today_daily = self._download_day(
                symbol,
                today.year,
                today.month,
                today.day,
                timeout_sec=day_timeout,
                max_retries=day_retries,
            )
            if today_daily is not None and not today_daily.empty:
                chunks.append(today_daily)
            if self._tick_enabled:
                today_m1 = self._fetch_today_m1_from_ticks(symbol, live_mode=live_mode)
                if not today_m1.empty:
                    chunks.append(today_m1)

        if not chunks:
            return pd.DataFrame()

        df = pd.concat(chunks).sort_index()
        df = df[~df.index.duplicated(keep="last")]
        return df.loc[start:end]

    def fetch_range(
        self,
        instrument: Instrument,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
        *,
        allow_empty: bool = False,
    ) -> pd.DataFrame:
        symbol = self._symbol(instrument)
        start = start.astimezone(timezone.utc)
        end = end.astimezone(timezone.utc)

        _log.info(
            "dukascopy_fetch_started",
            instrument=instrument.value,
            timeframe=timeframe.value,
            start=start.isoformat(),
            end=end.isoformat(),
        )

        with DUKASCOPY_LOCK:
            df = self._fetch_m1_hybrid(symbol, start, end)

        if df.empty:
            if allow_empty:
                return pd.DataFrame()
            raise DataError(
                f"No Dukascopy data for {instrument.value} between {start.date()} and {end.date()}"
            )

        if timeframe != Timeframe.M1:
            df = _resample_m1(df, timeframe)

        return df

    def fetch_m1_recent(
        self,
        instrument: Instrument,
        *,
        max_cache_age_sec: Optional[float] = None,
        lookback_hours: Optional[float] = None,
        wait_for_lock: bool = True,
    ) -> pd.DataFrame:
        """Fetch (or return cached) recent M1 window for live polling."""
        ttl = self._live_m1_cache_ttl_sec if max_cache_age_sec is None else max_cache_age_sec
        now_mono = time.monotonic()
        cached = self._m1_cache.get(instrument)
        if cached is not None and (now_mono - cached.fetched_at) < ttl:
            _log.debug(
                "dukascopy_m1_cache_hit",
                instrument=instrument.value,
                rows=len(cached.df),
            )
            return cached.df

        if not wait_for_lock and dukascopy_lock_held():
            if cached is not None:
                _log.debug(
                    "dukascopy_m1_cache_stale_fallback",
                    instrument=instrument.value,
                    rows=len(cached.df),
                )
                return cached.df
            _log.debug(
                "dukascopy_m1_fetch_skipped_busy",
                instrument=instrument.value,
            )
            return pd.DataFrame()

        now = datetime.now(timezone.utc)
        if lookback_hours is not None:
            lookback = timedelta(hours=lookback_hours)
        else:
            lookback = timedelta(days=self._live_m1_lookback_days)
        symbol = self._symbol(instrument)
        acquired = (
            DUKASCOPY_LOCK.acquire(blocking=True)
            if wait_for_lock
            else DUKASCOPY_LOCK.acquire(blocking=False)
        )
        if not acquired:
            if cached is not None:
                return cached.df
            return pd.DataFrame()
        try:
            df = self._fetch_m1_hybrid(symbol, now - lookback, now, live_mode=True)
        finally:
            DUKASCOPY_LOCK.release()
        if not df.empty:
            self._m1_cache[instrument] = _M1CacheEntry(df=df, fetched_at=now_mono)
        return df

    def live_bars_from_m1(
        self,
        instrument: Instrument,
        timeframe: Timeframe,
        m1_df: pd.DataFrame,
    ) -> tuple[OHLCVBar, Optional[OHLCVBar]]:
        """Build live bars for a timeframe from an already-fetched M1 window."""
        return bars_from_m1_df(instrument, timeframe, m1_df)

    def fetch_live_bars(
        self,
        instrument: Instrument,
        timeframe: Timeframe,
    ) -> tuple[OHLCVBar, Optional[OHLCVBar]]:
        m1_df = self.fetch_m1_recent(instrument)
        if m1_df.empty:
            raise DataError(f"Dukascopy live fetch returned no bars for {instrument.value}")
        return self.live_bars_from_m1(instrument, timeframe, m1_df)