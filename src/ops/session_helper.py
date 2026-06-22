"""Operations Session Helper for expected bar calculations."""

from __future__ import annotations

import pandas as pd
from src.core.contracts import Timeframe

# Mapping timeframes to pandas frequency strings
_FREQ_MAP = {
    Timeframe.M1: "1min",
    Timeframe.M5: "5min",
    Timeframe.M15: "15min",
    Timeframe.M30: "30min",
    Timeframe.H1: "1h",
    Timeframe.H4: "4h",
    Timeframe.D1: "1d",
}


def expected_bar_count(timeframe: Timeframe, year: int, month: int) -> int:
    """Calculate the expected number of Forex bars for a given month and timeframe.

    Filters out weekend hours (Friday 22:00 UTC to Sunday 22:00 UTC) where the
    Forex market is closed.
    """
    freq = _FREQ_MAP.get(timeframe)
    if not freq:
        # Fallback if frequency not found (e.g. weekly)
        return 0

    # Start and end of the month
    start = pd.Timestamp(year=year, month=month, day=1, tz="UTC")
    end = start + pd.offsets.MonthEnd(0) + pd.Timedelta(hours=23, minutes=59, seconds=59)

    # Generate complete DatetimeIndex for the month
    idx = pd.date_range(start=start, end=end, freq=freq, tz="UTC")

    # Filter out weekends (Friday 22:00 UTC to Sunday 22:00 UTC)
    # Friday is weekday 4, Saturday is 5, Sunday is 6
    # Market closes Friday at 22:00 (10 PM) and opens Sunday at 22:00 (10 PM)
    is_weekend = (
        (idx.weekday == 5) |  # Saturday
        ((idx.weekday == 4) & (idx.hour >= 22)) |  # Friday after 22:00
        ((idx.weekday == 6) & (idx.hour < 22))     # Sunday before 22:00
    )
    
    # D1 does not trade on weekends (weekday 5 and 6)
    if timeframe == Timeframe.D1:
        is_weekend = (idx.weekday == 5) | (idx.weekday == 6)

    # Expected bars is the count of open-market timestamps
    return int((~is_weekend).sum())
