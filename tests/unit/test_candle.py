"""Unit tests for shared UTC candle boundary helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from src.core.candle import candle_open_time, next_candle_close, tf_duration
from src.core.contracts import Timeframe


def _utc(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def test_candle_open_time_h1() -> None:
    dt = _utc(2024, 1, 15, 14, 37)
    assert candle_open_time(dt, Timeframe.H1) == _utc(2024, 1, 15, 14)


def test_candle_open_time_m15() -> None:
    dt = _utc(2024, 1, 15, 14, 37)
    assert candle_open_time(dt, Timeframe.M15) == _utc(2024, 1, 15, 14, 30)


def test_next_candle_close_h1() -> None:
    dt = _utc(2024, 1, 15, 14, 37)
    assert next_candle_close(dt, Timeframe.H1) == _utc(2024, 1, 15, 15)


def test_tf_duration_matches_timeframe() -> None:
    assert tf_duration(Timeframe.M1).total_seconds() == 60
    assert tf_duration(Timeframe.H1).total_seconds() == 3600