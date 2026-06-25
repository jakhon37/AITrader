"""Adaptive live-poll intervals aligned to candle close times."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.core.contracts import Timeframe

_TF_DURATION: dict[Timeframe, timedelta] = {
    Timeframe.M1: timedelta(minutes=1),
    Timeframe.M5: timedelta(minutes=5),
    Timeframe.M15: timedelta(minutes=15),
    Timeframe.M30: timedelta(minutes=30),
    Timeframe.H1: timedelta(hours=1),
    Timeframe.H4: timedelta(hours=4),
    Timeframe.D1: timedelta(days=1),
    Timeframe.W1: timedelta(weeks=1),
}

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


def _candle_open_time(dt: datetime, timeframe: Timeframe) -> datetime:
    dur = _TF_DURATION[timeframe]
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    elapsed = (dt.astimezone(timezone.utc) - epoch).total_seconds()
    dur_secs = dur.total_seconds()
    candle_epoch_secs = (elapsed // dur_secs) * dur_secs
    return epoch + timedelta(seconds=candle_epoch_secs)


def _next_candle_close(dt: datetime, timeframe: Timeframe) -> datetime:
    return _candle_open_time(dt, timeframe) + _TF_DURATION[timeframe]


def seconds_until_candle_close(now: datetime, timeframe: Timeframe) -> float:
    """Seconds until the active candle closes (UTC)."""
    now = now.astimezone(timezone.utc)
    return max(0.0, (_next_candle_close(now, timeframe) - now).total_seconds())


def compute_live_poll_interval(
    timeframe: Timeframe,
    now: datetime,
    *,
    focused: bool = True,
    background_multiplier: float = 2.0,
) -> float:
    """Return seconds until this pair should be polled again.

    Polls faster near candle close (forming bar), slower mid-candle.
    """
    now = now.astimezone(timezone.utc)
    dur = _TF_DURATION[timeframe].total_seconds()
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