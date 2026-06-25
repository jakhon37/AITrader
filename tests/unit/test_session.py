"""Tests for FX session UTC boundaries."""

from datetime import datetime, timezone

from src.core.contracts import Instrument
from src.core.session import (
    is_chart_bar,
    is_fx_session_open,
    is_gold_session_open,
    pip_size_for,
)


def _utc(y: int, m: int, d: int, h: int, minute: int = 0) -> datetime:
    return datetime(y, m, d, h, minute, tzinfo=timezone.utc)


def test_fx_session_friday_before_close() -> None:
    assert is_fx_session_open(_utc(2026, 6, 19, 21, 59)) is True


def test_fx_session_friday_at_close() -> None:
    assert is_fx_session_open(_utc(2026, 6, 19, 22, 0)) is False


def test_fx_session_saturday_closed() -> None:
    assert is_fx_session_open(_utc(2026, 6, 20, 3, 0)) is False


def test_fx_session_sunday_before_open() -> None:
    assert is_fx_session_open(_utc(2026, 6, 21, 21, 59)) is False


def test_fx_session_sunday_at_open() -> None:
    assert is_fx_session_open(_utc(2026, 6, 21, 22, 0)) is True


def test_gold_daily_break_hour() -> None:
    assert is_gold_session_open(_utc(2026, 6, 17, 20, 59)) is True
    assert is_gold_session_open(_utc(2026, 6, 17, 21, 0)) is False
    assert is_gold_session_open(_utc(2026, 6, 17, 21, 30)) is False
    assert is_gold_session_open(_utc(2026, 6, 17, 22, 0)) is True


def test_gold_weekly_close_friday() -> None:
    assert is_gold_session_open(_utc(2026, 6, 19, 20, 59)) is True
    assert is_gold_session_open(_utc(2026, 6, 19, 21, 0)) is False
    assert is_gold_session_open(_utc(2026, 6, 19, 23, 0)) is False


def test_gold_sunday_open() -> None:
    assert is_gold_session_open(_utc(2026, 6, 21, 21, 59)) is False
    assert is_gold_session_open(_utc(2026, 6, 21, 22, 0)) is True


def test_chart_bar_rejects_weekend_flat() -> None:
    ts = _utc(2026, 6, 20, 12, 0)
    assert (
        is_chart_bar(ts, Instrument.EURUSD, 1.1, 1.1, 1.1, 1.1, 0.0) is False
    )


def test_chart_bar_rejects_inactive_flat_during_session() -> None:
    ts = _utc(2026, 6, 17, 12, 0)
    assert (
        is_chart_bar(ts, Instrument.EURUSD, 1.1, 1.1, 1.1, 1.1, 0.0) is False
    )


def test_chart_bar_keeps_active_session_bar() -> None:
    ts = _utc(2026, 6, 17, 12, 0)
    assert (
        is_chart_bar(ts, Instrument.EURUSD, 1.1, 1.1005, 1.0995, 1.1002, 12.0)
        is True
    )


def test_chart_bar_gold_daily_break_rejected() -> None:
    ts = _utc(2026, 6, 17, 21, 0)
    assert (
        is_chart_bar(ts, Instrument.XAUUSD, 2345.0, 2345.1, 2344.9, 2345.0, 5.0)
        is False
    )


def test_pip_size_all_instruments() -> None:
    from src.core.session import reload_instrument_configs

    reload_instrument_configs()
    assert pip_size_for(Instrument.EURUSD) == 0.0001
    assert pip_size_for(Instrument.GBPUSD) == 0.0001
    assert pip_size_for(Instrument.USDJPY) == 0.01
    assert pip_size_for(Instrument.XAUUSD) == 0.01


def test_chart_bar_gbpusd_weekend_rejected() -> None:
    ts = _utc(2026, 6, 20, 12, 0)
    assert (
        is_chart_bar(ts, Instrument.GBPUSD, 1.27, 1.2701, 1.2699, 1.27, 10.0) is False
    )


def test_chart_bar_usdjpy_weekend_rejected() -> None:
    ts = _utc(2026, 6, 20, 12, 0)
    assert (
        is_chart_bar(ts, Instrument.USDJPY, 157.0, 157.1, 156.9, 157.0, 10.0)
        is False
    )