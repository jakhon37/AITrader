"""Adaptive live-poll intervals aligned to candle close times."""

from __future__ import annotations

from datetime import datetime, timezone

from src.core.candle import TF_DURATION, next_candle_close
from src.core.contracts import Timeframe

# (steady_min_sec, steady_max_sec) when not in the forming window
_STEADY_BOUNDS: dict[Timeframe, tuple[float, float]] = {
    Timeframe.M1: (30.0, 60.0),
    Timeframe.M5: (45.0, 120.0),
    Timeframe.M15: (60.0, 180.0),
    Timeframe.M30: (90.0, 300.0),
    Timeframe.H1: (120.0, 600.0),
    Timeframe.H4: (300.0, 1800.0),
    Timeframe.D1: (1800.0, 7200.0),
    Timeframe.W1: (3600.0, 14400.0),
}

_FORMING_FRAC = 0.08
_MIN_FORMING_SEC = 45.0
_MAX_FORMING_SEC = 180.0


def seconds_until_candle_close(now: datetime, timeframe: Timeframe) -> float:
    """Seconds until the active candle closes (UTC)."""
    now = now.astimezone(timezone.utc)
    return max(0.0, (next_candle_close(now, timeframe) - now).total_seconds())


def compute_live_poll_interval(
    timeframe: Timeframe,
    now: datetime,
    *,
    focused: bool = True,
    background_multiplier: float = 2.0,
) -> float:
    """Return seconds until this pair should be polled again."""
    now = now.astimezone(timezone.utc)
    dur = TF_DURATION[timeframe].total_seconds()
    secs_to_close = seconds_until_candle_close(now, timeframe)

    forming_window = max(
        _MIN_FORMING_SEC,
        min(_MAX_FORMING_SEC, dur * _FORMING_FRAC),
    )

    if secs_to_close <= forming_window:
        if timeframe == Timeframe.M1:
            fast = 15.0
        elif timeframe in (Timeframe.H4, Timeframe.D1, Timeframe.W1):
            fast = 60.0
        else:
            fast = 30.0
        interval = fast
    else:
        lo, hi = _STEADY_BOUNDS.get(timeframe, (60.0, dur * 0.25))
        target = secs_to_close * 0.2
        interval = max(lo, min(hi, target))

    if not focused:
        interval *= background_multiplier

    return interval


def m1_cache_ttl_sec(poll_interval_sec: float, *, floor: float = 30.0) -> float:
    """Reuse one M1 download for at least one poll cycle."""
    return max(floor, poll_interval_sec * 0.85)