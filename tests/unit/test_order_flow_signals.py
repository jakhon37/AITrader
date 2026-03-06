"""Tests for order flow signals."""

import numpy as np
import pandas as pd
import pytest

from features.order_flow_signals import (
    compute_all_order_flow_signals,
    compute_mfi,
    compute_obv,
    compute_volume_ratio,
    compute_volume_spike,
    compute_vwap,
)


@pytest.fixture
def sample_ohlcv():
    """Create sample OHLCV data."""
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    np.random.seed(42)
    
    close = 100 + np.cumsum(np.random.randn(100) * 0.5)
    high = close + np.abs(np.random.randn(100) * 0.3)
    low = close - np.abs(np.random.randn(100) * 0.3)
    open_ = close + np.random.randn(100) * 0.2
    volume = np.random.randint(1000, 10000, 100)
    
    return pd.DataFrame({
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }, index=dates)


def test_compute_volume_ratio(sample_ohlcv):
    """Test volume ratio calculation."""
    vol_ratio = compute_volume_ratio(sample_ohlcv, window=20)
    
    assert isinstance(vol_ratio, pd.Series)
    assert len(vol_ratio) == len(sample_ohlcv)
    assert vol_ratio.iloc[:19].isna().all()  # First 19 are NaN
    assert (vol_ratio.iloc[20:] > 0).all()  # Ratios are positive


def test_compute_obv(sample_ohlcv):
    """Test On-Balance Volume calculation."""
    obv = compute_obv(sample_ohlcv)
    
    assert isinstance(obv, pd.Series)
    assert len(obv) == len(sample_ohlcv)
    # OBV is cumulative
    assert not obv.isna().all()


def test_compute_obv_uptrend():
    """Test OBV increases in uptrend."""
    dates = pd.date_range("2024-01-01", periods=50, freq="D")
    df = pd.DataFrame({
        "open": 100,
        "high": 101,
        "low": 99,
        "close": np.linspace(100, 150, 50),  # Strong uptrend
        "volume": 1000,
    }, index=dates)
    
    obv = compute_obv(df)
    
    # OBV should generally increase in uptrend
    assert obv.iloc[-1] > obv.iloc[10]


def test_compute_vwap(sample_ohlcv):
    """Test VWAP calculation."""
    vwap = compute_vwap(sample_ohlcv)
    
    assert isinstance(vwap, pd.Series)
    assert len(vwap) == len(sample_ohlcv)
    assert (vwap > 0).all()  # VWAP is positive


def test_compute_vwap_close_to_price(sample_ohlcv):
    """Test VWAP is close to price range."""
    vwap = compute_vwap(sample_ohlcv)
    
    # VWAP should be within the price range
    assert (vwap >= sample_ohlcv["low"].min() * 0.9).all()
    assert (vwap <= sample_ohlcv["high"].max() * 1.1).all()


def test_compute_mfi(sample_ohlcv):
    """Test Money Flow Index calculation."""
    mfi = compute_mfi(sample_ohlcv, window=14)
    
    assert isinstance(mfi, pd.Series)
    assert len(mfi) == len(sample_ohlcv)
    # MFI is between 0 and 100
    valid_mfi = mfi.dropna()
    assert (valid_mfi >= 0).all()
    assert (valid_mfi <= 100).all()


def test_compute_volume_spike(sample_ohlcv):
    """Test volume spike detection."""
    spikes = compute_volume_spike(sample_ohlcv, window=20, threshold=2.0)
    
    assert isinstance(spikes, pd.Series)
    assert len(spikes) == len(sample_ohlcv)
    # Binary values
    assert set(spikes.unique()).issubset({0, 1})


def test_compute_volume_spike_detects_high_volume():
    """Test that high volume is detected as spike."""
    dates = pd.date_range("2024-01-01", periods=50, freq="D")
    volume = np.array([1000] * 25 + [5000] * 5 + [1000] * 20)  # Spike in middle
    
    df = pd.DataFrame({
        "open": 100,
        "high": 101,
        "low": 99,
        "close": 100,
        "volume": volume,
    }, index=dates)
    
    spikes = compute_volume_spike(df, window=10, threshold=2.0)
    
    # Should detect spikes around indices 25-30
    assert spikes.iloc[26:30].sum() > 0


def test_compute_all_order_flow_signals(sample_ohlcv):
    """Test computing all order flow signals."""
    signals = compute_all_order_flow_signals(sample_ohlcv)
    
    assert isinstance(signals, pd.DataFrame)
    assert len(signals) == len(sample_ohlcv)
    
    expected_cols = ["volume_ratio", "obv", "vwap", "mfi", "volume_spike"]
    for col in expected_cols:
        assert col in signals.columns


def test_compute_all_order_flow_signals_index_matches(sample_ohlcv):
    """Test that output index matches input."""
    signals = compute_all_order_flow_signals(sample_ohlcv)
    
    assert signals.index.equals(sample_ohlcv.index)


def test_volume_ratio_with_zero_volume():
    """Test handling of zero volume."""
    dates = pd.date_range("2024-01-01", periods=30, freq="D")
    df = pd.DataFrame({
        "open": 100,
        "high": 101,
        "low": 99,
        "close": 100,
        "volume": 0,  # Zero volume
    }, index=dates)
    
    vol_ratio = compute_volume_ratio(df, window=10)
    
    # Should handle division by zero gracefully
    assert len(vol_ratio) == len(df)


def test_order_flow_signals_with_constant_price():
    """Test order flow with constant prices."""
    dates = pd.date_range("2024-01-01", periods=50, freq="D")
    df = pd.DataFrame({
        "open": 100,
        "high": 100,
        "low": 100,
        "close": 100,  # Constant price
        "volume": np.random.randint(1000, 5000, 50),
    }, index=dates)
    
    signals = compute_all_order_flow_signals(df)
    
    # Should not crash
    assert len(signals) == len(df)
    # OBV should be flat
    assert signals["obv"].iloc[-1] == signals["obv"].iloc[10]
