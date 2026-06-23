"""Shared utility helpers for replay sessions."""
from __future__ import annotations

from datetime import timedelta


def get_buffer_duration(timeframe: "Timeframe") -> timedelta:  # type: ignore[name-defined]
    """Return the sliding window size for bar-chunk loading based on timeframe."""
    from src.core.contracts import Timeframe

    if timeframe == Timeframe.M1:
        return timedelta(days=3)
    elif timeframe == Timeframe.M5:
        return timedelta(days=15)
    elif timeframe == Timeframe.M15:
        return timedelta(days=45)
    elif timeframe == Timeframe.M30:
        return timedelta(days=90)
    elif timeframe == Timeframe.H1:
        return timedelta(days=180)
    else:
        return timedelta(days=365 * 5)
