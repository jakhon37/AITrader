"""Dukascopy hourly tick .bi5 → M1 OHLCV aggregation (for current UTC day)."""

from __future__ import annotations

import lzma
import struct
from datetime import datetime, timezone

import pandas as pd

from src.core.logging import get_logger

_log = get_logger("D02-DATA")

TICK_RECORD_FMT = ">IIIff"
TICK_RECORD_SIZE = struct.calcsize(TICK_RECORD_FMT)


def parse_tick_hour(
    content: bytes,
    year: int,
    month: int,
    day: int,
    hour: int,
    divisor: float,
) -> pd.DataFrame:
    """Parse one hour of BID/ASK ticks into a DataFrame."""
    decompressed = lzma.decompress(content)
    num_records = len(decompressed) // TICK_RECORD_SIZE
    if num_records == 0:
        return pd.DataFrame()

    base_dt = datetime(year, month, day, hour, tzinfo=timezone.utc)
    rows: list[dict[str, float | datetime]] = []
    for i in range(num_records):
        offset = i * TICK_RECORD_SIZE
        chunk = decompressed[offset : offset + TICK_RECORD_SIZE]
        ms, ask_i, bid_i, ask_vol, bid_vol = struct.unpack(TICK_RECORD_FMT, chunk)
        rows.append(
            {
                "timestamp": base_dt + pd.Timedelta(milliseconds=int(ms)),
                "bid": bid_i / divisor,
                "ask": ask_i / divisor,
                "volume": float(ask_vol) + float(bid_vol),
            }
        )

    df = pd.DataFrame(rows).set_index("timestamp")
    return df[["bid", "ask", "volume"]]


def ticks_to_m1(ticks: pd.DataFrame) -> pd.DataFrame:
    """Aggregate tick stream to M1 OHLCV using BID (matches BID_candles_min_1)."""
    if ticks.empty:
        return pd.DataFrame()

    ticks = ticks.sort_index()
    resampler = ticks["bid"].resample("1min", label="left", closed="left")
    m1 = pd.DataFrame()
    m1["open"] = resampler.first()
    m1["high"] = resampler.max()
    m1["low"] = resampler.min()
    m1["close"] = resampler.last()
    m1["volume"] = ticks["volume"].resample("1min", label="left", closed="left").sum()
    return m1.dropna()


def fetch_today_m1_from_ticks(
    download_hour,
    *,
    now: datetime | None = None,
) -> pd.DataFrame:
    """Fetch all available tick hours for the current UTC day and return M1 bars."""
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    chunks: list[pd.DataFrame] = []
    for hour in range(now.hour + 1):
        hour_df = download_hour(now.year, now.month, now.day, hour)
        if hour_df is not None and not hour_df.empty:
            chunks.append(hour_df)

    if not chunks:
        return pd.DataFrame()

    combined = pd.concat(chunks).sort_index()
    m1 = ticks_to_m1(combined)
    return m1.loc[:now]