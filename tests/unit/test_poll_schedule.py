"""Tests for adaptive live poll scheduling."""

from datetime import datetime, timezone

from src.core.contracts import Timeframe
from src.core.poll_schedule import compute_live_poll_interval, seconds_until_candle_close


def _utc(y: int, m: int, d: int, h: int, minute: int = 0) -> datetime:
    return datetime(y, m, d, h, minute, tzinfo=timezone.utc)


def test_h1_mid_candle_polls_slowly() -> None:
    # 9:15 UTC → 45 min to close; should not poll every 2s
    now = _utc(2026, 6, 17, 9, 15)
    interval = compute_live_poll_interval(Timeframe.H1, now, focused=True)
    assert interval >= 120.0


def test_h1_near_close_polls_faster() -> None:
    now = _utc(2026, 6, 17, 9, 58)
    interval = compute_live_poll_interval(Timeframe.H1, now, focused=True)
    assert interval <= 60.0


def test_d1_mid_day_polls_very_slowly() -> None:
    now = _utc(2026, 6, 17, 12, 0)
    interval = compute_live_poll_interval(Timeframe.D1, now, focused=True)
    assert interval >= 1800.0


def test_seconds_until_h1_close() -> None:
    now = _utc(2026, 6, 17, 9, 40)
    assert seconds_until_candle_close(now, Timeframe.H1) == 20 * 60