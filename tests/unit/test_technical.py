"""Unit and integration tests for D04-TECHNICAL division."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import numpy as np
import pandas as pd
import pytest

from src.core.bus import InProcessBus
from src.core.contracts import (
    Instrument,
    Timeframe,
    Direction,
    SignalStrength,
    MarketRegime,
    OHLCVBar,
    TechnicalSignal,
    BusChannel,
)
from src.core.config import InstrumentConfig
from src.data.store import DataStore
from src.technical.loader import MultiTFDataset, TechnicalDataLoader
from src.technical.indicators import (
    compute_adx,
    compute_stochastic,
    compute_obv,
    compute_vwap,
    compute_swing_pivots,
    compute_sr_distance,
    compute_indicators,
)
from src.technical.regime import detect_regime, detect_regime_series
from src.technical.confluence import compute_tf_bias, ConfluenceCombiner
from src.technical.signal_builder import TechnicalSignalBuilder
from src.technical.engine import TechnicalEngine


@pytest.fixture()
def sample_ohlcv() -> pd.DataFrame:
    """Create a sample OHLCV DataFrame for testing."""
    dates = pd.date_range("2024-01-01", periods=250, freq="h", tz="UTC")
    np.random.seed(42)
    # Start price at 1.1000
    close = 1.1000 + np.cumsum(np.random.randn(250) * 0.001)
    high = close + np.abs(np.random.randn(250) * 0.0005)
    low = close - np.abs(np.random.randn(250) * 0.0005)
    open_ = close + np.random.randn(250) * 0.0002
    volume = np.random.randint(100, 1000, 250).astype(float)

    return pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        },
        index=dates,
    )


# ── Indicators Tests ──────────────────────────────────────────────────────────

def test_custom_indicators(sample_ohlcv):
    adx = compute_adx(sample_ohlcv, 14)
    assert isinstance(adx, pd.Series)
    assert len(adx) == len(sample_ohlcv)
    assert not adx.dropna().empty

    stoch = compute_stochastic(sample_ohlcv, 14, 3)
    assert isinstance(stoch, pd.DataFrame)
    assert "stoch_k" in stoch.columns
    assert "stoch_d" in stoch.columns

    obv = compute_obv(sample_ohlcv)
    assert isinstance(obv, pd.Series)
    assert len(obv) == len(sample_ohlcv)

    vwap = compute_vwap(sample_ohlcv)
    assert isinstance(vwap, pd.Series)
    assert len(vwap) == len(sample_ohlcv)

    pivots = compute_swing_pivots(sample_ohlcv, 3)
    assert isinstance(pivots, pd.DataFrame)
    assert "swing_high" in pivots.columns
    assert "swing_low" in pivots.columns

    sr = compute_sr_distance(sample_ohlcv, 3)
    assert "dist_support" in sr.columns
    assert "dist_resistance" in sr.columns


def test_compute_indicators_dict(sample_ohlcv):
    timeframes = {Timeframe.H1: sample_ohlcv}
    results = compute_indicators(timeframes)
    
    assert Timeframe.H1 in results
    indicators = results[Timeframe.H1]
    
    expected_keys = [
        "close", "ema_20", "ema_50", "ema_200", "adx", "rsi", "stoch_k", "stoch_d",
        "macd", "macd_signal", "macd_hist", "atr", "bb_middle", "bb_upper",
        "bb_lower", "bb_width", "obv", "vwap", "support", "resistance",
        "dist_support", "dist_resistance"
    ]
    for key in expected_keys:
        assert key in indicators
        assert isinstance(indicators[key], float)


# ── Regime Tests ──────────────────────────────────────────────────────────────

def test_detect_regime_volatile(sample_ohlcv):
    # Simulate a high volatility period at the end
    df_vol = sample_ohlcv.copy()
    # Spike the high/low ranges for the last 5 bars
    df_vol.loc[df_vol.index[-5:], "high"] += 0.05
    df_vol.loc[df_vol.index[-5:], "low"] -= 0.05
    df_vol.loc[df_vol.index[-5:], "close"] += 0.02
    
    regime = detect_regime(df_vol)
    assert regime == MarketRegime.VOLATILE


def test_detect_regime_trending(sample_ohlcv):
    # Simulate a strong trend with low volatility and high ADX
    df_trend = sample_ohlcv.copy()
    # Gradually increase close prices over the last 50 bars to establish a clear trend above EMA200
    trend_addition = np.linspace(0, 0.2, 50)
    df_trend.loc[df_trend.index[-50:], "close"] += trend_addition
    df_trend.loc[df_trend.index[-50:], "high"] += trend_addition
    df_trend.loc[df_trend.index[-50:], "low"] += trend_addition
    
    # Run regime series and check if TRENDING is detected
    series = detect_regime_series(df_trend)
    assert MarketRegime.TRENDING in series.values


# ── Confluence Tests ──────────────────────────────────────────────────────────

def test_compute_tf_bias():
    # Bullish indicators
    bullish_inds = {
        "ema_20": 1.1100, "ema_50": 1.1000, "ema_200": 1.0500, "close": 1.1200,
        "rsi": 65.0, "macd_hist": 0.0010, "stoch_k": 70.0, "stoch_d": 60.0,
        "bb_middle": 1.1050
    }
    direction, confidence = compute_tf_bias(Timeframe.H1, bullish_inds, MarketRegime.TRENDING)
    assert direction == Direction.LONG
    assert confidence > 0.5

    # Bearish indicators
    bearish_inds = {
        "ema_20": 1.0900, "ema_50": 1.1000, "ema_200": 1.1500, "close": 1.0800,
        "rsi": 35.0, "macd_hist": -0.0010, "stoch_k": 30.0, "stoch_d": 40.0,
        "bb_middle": 1.0950
    }
    direction, confidence = compute_tf_bias(Timeframe.H1, bearish_inds, MarketRegime.TRENDING)
    assert direction == Direction.SHORT
    assert confidence > 0.5


def test_confluence_combiner():
    combiner = ConfluenceCombiner(Timeframe.H1)
    
    from src.core.contracts import TimeframeBias
    biases = [
        TimeframeBias(
            timeframe=Timeframe.H4, direction=Direction.LONG, confidence=0.8,
            regime=MarketRegime.TRENDING, indicators={}, support=None, resistance=None
        ),
        TimeframeBias(
            timeframe=Timeframe.H1, direction=Direction.LONG, confidence=0.7,
            regime=MarketRegime.TRENDING, indicators={}, support=None, resistance=None
        ),
        TimeframeBias(
            timeframe=Timeframe.M15, direction=Direction.LONG, confidence=0.6,
            regime=MarketRegime.TRENDING, indicators={}, support=None, resistance=None
        ),
    ]
    consensus_dir, consensus_conf, confluence_score = combiner.combine(biases)
    assert consensus_dir == Direction.LONG
    assert confluence_score == 1.0
    # Bonus for 3 TFs agreeing applied (confidence += 0.10)
    assert consensus_conf > 0.7


# ── Signal Builder Tests ──────────────────────────────────────────────────────

def test_signal_builder():
    builder = TechnicalSignalBuilder(Timeframe.H1)
    indicators = {"close": 1.1000, "atr": 0.0020}
    timestamp = datetime(2024, 6, 21, 10, 0, tzinfo=timezone.utc)
    
    signal = builder.build(
        instrument=Instrument.EURUSD,
        timestamp=timestamp,
        direction=Direction.LONG,
        confidence=0.8,
        confluence_score=0.9,
        per_timeframe=[],
        primary_indicators=indicators,
        primary_regime=MarketRegime.TRENDING,
    )
    
    assert isinstance(signal, TechnicalSignal)
    assert signal.instrument == Instrument.EURUSD
    assert signal.direction == Direction.LONG
    assert signal.confidence == 0.8
    assert signal.strength == SignalStrength.STRONG
    assert signal.entry_price == 1.1000
    assert signal.stop_loss == 1.1000 - 1.5 * 0.0020
    assert signal.take_profit == 1.1000 + 2.5 * 0.0020
    assert signal.valid_until == timestamp + timedelta(hours=1)


# ── Engine Integration Tests ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_technical_engine_pipeline(tmp_path, sample_ohlcv):
    bus = InProcessBus()
    store = DataStore(base_dir=tmp_path)
    
    # Set up config
    inst_config = {
        Instrument.EURUSD: InstrumentConfig(
            pip_size=0.0001,
            lot_size=100000.0,
            session_hours={"open": "22:00", "close": "22:00"},
            active_timeframes=[Timeframe.M15, Timeframe.H1],
            primary_timeframe=Timeframe.H1,
        )
    }

    # Populate DataStore with sample H1 and M15 data
    # Ensure they have timezone-aware indexes
    df_h1 = sample_ohlcv.copy()
    df_m15 = sample_ohlcv.copy()
    # Change M15 index to have 15m intervals
    df_m15.index = pd.date_range(sample_ohlcv.index[0], periods=len(sample_ohlcv), freq="15min", tz="UTC")

    store.write_ohlcv(Instrument.EURUSD, Timeframe.H1, df_h1)
    store.write_ohlcv(Instrument.EURUSD, Timeframe.M15, df_m15)

    engine = TechnicalEngine(
        bus=bus,
        store=store,
        instruments_config=inst_config,
    )

    received_signals = []

    async def signal_handler(payload):
        received_signals.append(payload)

    await bus.subscribe(BusChannel.TECHNICAL_SIGNAL, signal_handler)
    await engine.start()

    # Trigger pipeline by publishing an H1 bar close
    trigger_bar = OHLCVBar(
        signal_id="trigger_bar_id",
        instrument=Instrument.EURUSD,
        timeframe=Timeframe.H1,
        timestamp=sample_ohlcv.index[-1],  # open time of last bar
        open=sample_ohlcv["open"].iloc[-1],
        high=sample_ohlcv["high"].iloc[-1],
        low=sample_ohlcv["low"].iloc[-1],
        close=sample_ohlcv["close"].iloc[-1],
        volume=sample_ohlcv["volume"].iloc[-1],
        source="csv",
    )

    await bus.publish(BusChannel.OHLCV_BAR, trigger_bar)
    
    # Wait slightly for async queues
    await asyncio.sleep(0.1)

    await engine.stop()

    assert len(received_signals) == 1
    sig = received_signals[0]
    assert isinstance(sig, TechnicalSignal)
    assert sig.instrument == Instrument.EURUSD
    assert sig.primary_tf == Timeframe.H1
    assert sig.direction in [Direction.LONG, Direction.SHORT, Direction.NEUTRAL]
