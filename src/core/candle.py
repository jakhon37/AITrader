"""Shared UTC candle boundary helpers (D01 — used by D02 poll + feeds)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.core.contracts import Timeframe

TF_DURATION: dict[Timeframe, timedelta] = {
    Timeframe.M1: timedelta(minutes=1),
    Timeframe.M5: timedelta(minutes=5),
    Timeframe.M15: timedelta(minutes=15),
    Timeframe.M30: timedelta(minutes=30),
    Timeframe.H1: timedelta(hours=1),
    Timeframe.H4: timedelta(hours=4),
    Timeframe.D1: timedelta(days=1),
    Timeframe.W1: timedelta(weeks=1),
}


def candle_open_time(dt: datetime, timeframe: Timeframe) -> datetime:
    """Return the open time of the candle that contains ``dt`` (UTC)."""
    dur = TF_DURATION[timeframe]
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    elapsed = (dt.astimezone(timezone.utc) - epoch).total_seconds()
    dur_secs = dur.total_seconds()
    candle_epoch_secs = (elapsed // dur_secs) * dur_secs
    return epoch + timedelta(seconds=candle_epoch_secs)


def next_candle_close(dt: datetime, timeframe: Timeframe) -> datetime:
    """Return the close time (= open of next candle) after ``dt``."""
    return candle_open_time(dt, timeframe) + TF_DURATION[timeframe]


def tf_duration(timeframe: Timeframe) -> timedelta:
    """Duration of one bar for ``timeframe``."""
    return TF_DURATION[timeframe]