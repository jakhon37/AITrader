"""Tests for MT4-style scalping indicator stack."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from src.core.config import InstrumentConfig
from src.core.contracts import Direction, Instrument, MarketRegime, Timeframe
from src.technical.indicators import compute_indicators, uses_scalping_stack
from src.technical.scalping.indicators import (
    compute_heiken_ashi,
    compute_hull_ma,
    compute_scalping_series,
    latest_scalping_values,
)
from src.technical.scalping.scoring import compute_entry_trigger, compute_scalping_tf_bias
from src.technical.scalping.sessions import active_scalping_session, is_scalping_session_open


@pytest.fixture()
def gold_ohlcv() -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=300, freq="15min", tz="UTC")
    np.random.seed(7)
    close = 1900.0 + np.cumsum(np.random.randn(300) * 0.8)
    high = close + np.abs(np.random.randn(300) * 0.4)
    low = close - np.abs(np.random.randn(300) * 0.4)
    open_ = close + np.random.randn(300) * 0.2
    volume = np.random.randint(100, 5000, 300).astype(float)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=dates,
    )


def test_uses_scalping_stack_from_instrument_config():
    cfg_on = InstrumentConfig(
        pip_size=0.01,
        lot_size=100,
        session_hours={"open": "22:00", "close": "21:00"},
        active_timeframes=[Timeframe.M15],
        primary_timeframe=Timeframe.M15,
        scalping_mode=True,
    )
    cfg_off = InstrumentConfig(
        pip_size=0.0001,
        lot_size=100000,
        session_hours={"open": "22:00", "close": "22:00"},
        active_timeframes=[Timeframe.H1],
        primary_timeframe=Timeframe.H1,
        scalping_mode=False,
    )
    assert uses_scalping_stack(instrument_config=cfg_on) is True
    assert uses_scalping_stack(instrument_config=cfg_off) is False
    assert uses_scalping_stack(None) is False


def test_uses_scalping_stack_from_yaml():
    assert uses_scalping_stack(Instrument.XAUUSD) is True
    assert uses_scalping_stack(Instrument.EURUSD) is False


def test_heiken_ashi_and_hull(gold_ohlcv):
    ha = compute_heiken_ashi(gold_ohlcv)
    assert {"ha_open", "ha_close"}.issubset(ha.columns)
    assert len(ha) == len(gold_ohlcv)

    hull = compute_hull_ma(gold_ohlcv["close"])
    assert hull.notna().sum() > 50


def test_latest_scalping_values(gold_ohlcv):
    values = latest_scalping_values(gold_ohlcv)
    expected = {
        "close",
        "atr_110",
        "ha_bullish",
        "hull_slope",
        "joker",
        "band_position",
        "sb_macd_hist",
        "sb_rsi",
        "sb_cci",
    }
    assert expected.issubset(values.keys())
    assert values["close"] > 0
    assert 0.0 <= values["joker"] <= 1.0


def test_compute_indicators_xauusd_includes_scalping(gold_ohlcv):
    results = compute_indicators({Timeframe.M15: gold_ohlcv}, instrument=Instrument.XAUUSD)
    inds = results[Timeframe.M15]
    assert "close" in inds
    assert "band_position" in inds
    assert "trend_up_pct" not in inds  # meta added at bias stage


def test_scalping_tf_bias_bearish_at_top_band():
    indicators = {
        "close": 1950.0,
        "atr_110": 8.0,
        "ha_bullish": 0.0,
        "hull_slope": -2.0,
        "joker": 0.35,
        "band_position": 0.92,
        "sb_macd_hist": -0.5,
        "sb_rsi": 35.0,
        "sb_cci": -80.0,
        "sb_ema_fast": 1948.0,
        "sb_ema_slow": 1952.0,
    }
    direction, confidence, meta = compute_scalping_tf_bias(indicators, MarketRegime.TRENDING)
    assert direction == Direction.SHORT
    assert confidence > 0.0
    assert meta["trend_down_pct"] > meta["trend_up_pct"]


def test_entry_trigger_short_at_resistance():
    indicators = {
        "band_position": 0.9,
        "ha_bullish": 0.0,
        "hull_slope": -1.0,
        "joker": 0.4,
        "sb_macd_hist": -0.2,
    }
    assert compute_entry_trigger(indicators, Direction.SHORT) is True


def test_session_windows_utc():
    eu_time = datetime(2024, 6, 3, 12, 0, tzinfo=timezone.utc)
    assert active_scalping_session(eu_time) == "eu"
    assert is_scalping_session_open(eu_time) is True

    quiet = datetime(2024, 6, 3, 9, 0, tzinfo=timezone.utc)
    assert is_scalping_session_open(quiet) is False


def test_scalping_series_not_empty(gold_ohlcv):
    series = compute_scalping_series(gold_ohlcv)
    assert not series.empty
    assert "fl_outer_upper" in series.columns