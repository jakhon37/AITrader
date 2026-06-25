"""Multi-instrument registry and gap-fill tests."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from src.core.config import InstrumentConfig, SignalDecayConfig
from src.core.contracts import Instrument, Timeframe
from src.core.gap_fill import store_needs_gap_fill
from src.core.instruments import get_enabled_instruments


def _utc(y: int, m: int, d: int, h: int = 0, minute: int = 0) -> datetime:
    return datetime(y, m, d, h, minute, tzinfo=timezone.utc)


def _inst_cfg(*, enabled: bool = True, pip: float = 0.0001) -> InstrumentConfig:
    return InstrumentConfig(
        enabled=enabled,
        pip_size=pip,
        lot_size=100_000,
        session_hours={"open": "22:00", "close": "22:00"},
        active_timeframes=[Timeframe.H1],
        primary_timeframe=Timeframe.H1,
        signal_decay=SignalDecayConfig(),
    )


def _mock_instruments(**kwargs: InstrumentConfig) -> dict[Instrument, InstrumentConfig]:
    base = {inst: _inst_cfg() for inst in Instrument}
    for inst, cfg in kwargs.items():
        base[inst] = cfg
    return base


def test_get_enabled_instruments_all_four() -> None:
    with patch("src.core.instruments.load_instruments", return_value=_mock_instruments()):
        assert get_enabled_instruments() == [
            Instrument.EURUSD,
            Instrument.GBPUSD,
            Instrument.USDJPY,
            Instrument.XAUUSD,
        ]


def test_get_enabled_instruments_respects_disabled() -> None:
    configs = _mock_instruments(
        GBPUSD=_inst_cfg(enabled=False),
        XAUUSD=_inst_cfg(enabled=False),
    )
    with patch("src.core.instruments.load_instruments", return_value=configs):
        assert get_enabled_instruments() == [Instrument.EURUSD, Instrument.USDJPY]


def test_store_needs_gap_fill_when_empty() -> None:
    store = MagicMock()
    store.list_ohlcv_range.return_value = (None, None)
    assert store_needs_gap_fill(
        store,
        Instrument.GBPUSD,
        Timeframe.H1,
        _utc(2026, 6, 17, 12),
        auto_refresh=True,
    )


def test_store_needs_gap_fill_when_fresh() -> None:
    store = MagicMock()
    store.list_ohlcv_range.return_value = (
        _utc(2026, 6, 17, 10),
        _utc(2026, 6, 17, 11),
    )
    assert not store_needs_gap_fill(
        store,
        Instrument.USDJPY,
        Timeframe.H1,
        _utc(2026, 6, 17, 11, 30),
        auto_refresh=True,
    )


def test_store_needs_gap_fill_all_instruments_when_empty() -> None:
    store = MagicMock()
    store.list_ohlcv_range.return_value = (None, None)
    end = _utc(2026, 6, 17, 12)
    for inst in (Instrument.EURUSD, Instrument.GBPUSD, Instrument.USDJPY, Instrument.XAUUSD):
        assert store_needs_gap_fill(store, inst, Timeframe.H1, end, auto_refresh=True)


def test_xauusd_daily_break_in_instruments_yaml() -> None:
    from src.core.config import load_instruments

    configs = load_instruments()
    gold = configs[Instrument.XAUUSD]
    assert gold.daily_break is not None
    assert gold.daily_break.start == "21:00"
    assert gold.daily_break.end == "22:00"