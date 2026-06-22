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
            start_time = estimate_start_time(current_time, tf, num_bars)
            
            try:
                df = self.store.get_ohlcv(instrument, tf, start_time, current_time)
            except Exception:
                # Fallback to empty DataFrame if store has no data for this range
                df = pd.DataFrame()
                
            if not df.empty:
                # Ensure the DatetimeIndex has timezone UTC
                if df.index.tz is None:
                    df.index = df.index.tz_localize("UTC")
                
                # Exclude the bar if its end time (open time + duration) is after current_time
                delta = timeframe_to_timedelta(tf)
                df = df[df.index + delta <= current_time]
                
                # Keep only the last num_bars
                df = df.tail(num_bars)
            
            tf_data[tf] = df
            
        return MultiTFDataset(instrument=instrument, timeframes=tf_data)
