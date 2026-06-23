"""Multi-timeframe data loader for D04-TECHNICAL.

Fetches historical OHLCV data from DataStore and aligns them to the current time,
preventing future look-ahead leakage.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import pandas as pd

from src.core.contracts import Instrument, Timeframe
from src.data.store import DataStore


class MultiTFDataset:
    """Container for multi-timeframe OHLCV data."""

    def __init__(self, instrument: Instrument, timeframes: dict[Timeframe, pd.DataFrame]) -> None:
        self.instrument = instrument
        self.timeframes = timeframes


def timeframe_to_timedelta(tf: Timeframe) -> timedelta:
    """Convert a Timeframe enum to a timedelta object."""
    if tf == Timeframe.M1:
        return timedelta(minutes=1)
    elif tf == Timeframe.M5:
        return timedelta(minutes=5)
    elif tf == Timeframe.M15:
        return timedelta(minutes=15)
    elif tf == Timeframe.M30:
        return timedelta(minutes=30)
    elif tf == Timeframe.H1:
        return timedelta(hours=1)
    elif tf == Timeframe.H4:
        return timedelta(hours=4)
    elif tf == Timeframe.D1:
        return timedelta(days=1)
    elif tf == Timeframe.W1:
        return timedelta(weeks=1)
    else:
        raise ValueError(f"Unknown timeframe: {tf}")


def estimate_start_time(end: datetime, tf: Timeframe, num_bars: int) -> datetime:
    """Estimate a start time looking back far enough to get num_bars, accounting for weekends."""
    delta = timeframe_to_timedelta(tf)
    # Standard lookback factor of 2.0 to cover weekends and session gaps
    lookback = delta * num_bars * 2.0
    return end - lookback


class TechnicalDataLoader:
    """Loads and filters multi-timeframe historical data from DataStore."""

    def __init__(self, store: DataStore) -> None:
        self.store = store
        self._cache: dict[tuple[Instrument, Timeframe], pd.DataFrame] = {}

    def load(
        self,
        instrument: Instrument,
        timeframes: list[Timeframe],
        current_time: datetime,
        num_bars: int = 250,
    ) -> MultiTFDataset:
        """Fetch and return a MultiTFDataset for the given instrument and timeframes.

        Filters out any bars that are not fully closed at `current_time`.
        """
        tf_data = {}
        for tf in timeframes:
            cache_key = (instrument, tf)
            if cache_key not in self._cache:
                # Cache a broad range of data around current_time to avoid repeated disk reads.
                # Backtests/replays typically span up to a few years, so we cache 1 year back and forward.
                start_query = current_time - timedelta(days=366)
                end_query = current_time + timedelta(days=366)
                try:
                    df_full = self.store.get_ohlcv(instrument, tf, start_query, end_query)
                    if df_full.index.tz is None:
                        df_full.index = df_full.index.tz_localize("UTC")
                    self._cache[cache_key] = df_full
                except Exception:
                    self._cache[cache_key] = pd.DataFrame()

            df_cached = self._cache[cache_key]
            start_time = estimate_start_time(current_time, tf, num_bars)
            
            if not df_cached.empty:
                # Slice in-memory
                df = df_cached.loc[start_time:current_time]
                
                # Exclude the bar if its end time (open time + duration) is after current_time
                delta = timeframe_to_timedelta(tf)
                df = df[df.index + delta <= current_time]
                
                # Keep only the last num_bars
                df = df.tail(num_bars)
            else:
                df = pd.DataFrame()
                
            tf_data[tf] = df
            
        return MultiTFDataset(instrument=instrument, timeframes=tf_data)
