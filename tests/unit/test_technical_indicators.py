"""Tests for technical indicators."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from technical.indicators import (
    compute_all_indicators,
    compute_atr,
    compute_bollinger_bands,
    compute_ema,
    compute_garch_inputs,
    compute_macd,
    compute_returns,
    compute_rsi,
    compute_sma,
    compute_volatility,
)


@pytest.fixture
def sample_ohlcv() -> pd.DataFrame:
    """Create sample OHLCV data for testing."""
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    np.random.seed(42)

    close = 100 + np.cumsum(np.random.randn(100) * 0.5)
    high = close + np.abs(np.random.randn(100) * 0.3)
    low = close - np.abs(np.random.randn(100) * 0.3)
    open_ = close + np.random.randn(100) * 0.2

    return pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": np.random.randint(1000, 10000, 100),
        },
        index=dates,
    )


def test_compute_returns_simple(sample_ohlcv):
    """Test simple returns calculation."""
    returns = compute_returns(sample_ohlcv, periods=1, log_returns=False)

    assert isinstance(returns, pd.Series)
    assert len(returns) == len(sample_ohlcv)
    assert pd.isna(returns.iloc[0])  # First value is NaN
    assert not returns.iloc[1:].isna().all()


def test_compute_returns_log(sample_ohlcv):
    """Test log returns calculation."""
    returns = compute_returns(sample_ohlcv, periods=1, log_returns=True)

    assert isinstance(returns, pd.Series)
    assert pd.isna(returns.iloc[0])
    # Log returns should be close to simple returns for small changes
    simple_ret = compute_returns(sample_ohlcv, periods=1, log_returns=False)
    np.testing.assert_allclose(returns.iloc[1:10], simple_ret.iloc[1:10], atol=0.01)


def test_compute_returns_multiperiod(sample_ohlcv):
    """Test multi-period returns."""
    returns_5 = compute_returns(sample_ohlcv, periods=5)

    assert len(returns_5) == len(sample_ohlcv)
    assert returns_5.iloc[:5].isna().sum() == 5  # First 5 are NaN


def test_compute_volatility_std(sample_ohlcv):
    """Test standard deviation volatility."""
    vol = compute_volatility(sample_ohlcv, window=20, method="std")

    assert isinstance(vol, pd.Series)
    assert len(vol) == len(sample_ohlcv)
    assert vol.iloc[:19].isna().all()  # First 19 are NaN
    assert (vol.iloc[20:] > 0).all()  # Volatility is positive


def test_compute_volatility_parkinson(sample_ohlcv):
    """Test Parkinson volatility."""
    vol = compute_volatility(sample_ohlcv, window=20, method="parkinson")

    assert isinstance(vol, pd.Series)
    assert (vol.iloc[20:] > 0).all()


def test_compute_volatility_garman_klass(sample_ohlcv):
    """Test Garman-Klass volatility."""
    vol = compute_volatility(sample_ohlcv, window=20, method="garman_klass")

    assert isinstance(vol, pd.Series)
    assert (vol.iloc[20:] > 0).all()


def test_compute_volatility_invalid_method(sample_ohlcv):
    """Test invalid volatility method raises error."""
    with pytest.raises(ValueError, match="Unknown volatility method"):
        compute_volatility(sample_ohlcv, method="invalid")


def test_compute_ema(sample_ohlcv):
    """Test Exponential Moving Average."""
    ema = compute_ema(sample_ohlcv["close"], span=12)

    assert isinstance(ema, pd.Series)
    assert len(ema) == len(sample_ohlcv)
    assert not ema.isna().all()
    # EMA should be smoother than original
    assert ema.std() < sample_ohlcv["close"].std()


def test_compute_sma(sample_ohlcv):
    """Test Simple Moving Average."""
    sma = compute_sma(sample_ohlcv["close"], window=20)

    assert isinstance(sma, pd.Series)
    assert len(sma) == len(sample_ohlcv)
    assert sma.iloc[:19].isna().all()  # First 19 are NaN
    assert not sma.iloc[20:].isna().any()


def test_compute_atr(sample_ohlcv):
    """Test Average True Range."""
    atr = compute_atr(sample_ohlcv, window=14)

    assert isinstance(atr, pd.Series)
    assert len(atr) == len(sample_ohlcv)
    assert (atr.iloc[14:] > 0).all()  # ATR is always positive


def test_compute_atr_measures_volatility(sample_ohlcv):
    """Test that ATR increases with volatility."""
    # Create high volatility period
    high_vol_df = sample_ohlcv.copy()
    high_vol_df.iloc[50:70, :4] *= 1.5  # Increase OHLC values

    atr = compute_atr(high_vol_df, window=14)

    # ATR should be higher during high volatility period
    assert atr.iloc[65] > atr.iloc[45]


def test_compute_rsi(sample_ohlcv):
    """Test Relative Strength Index."""
    rsi = compute_rsi(sample_ohlcv["close"], window=14)

    assert isinstance(rsi, pd.Series)
    assert len(rsi) == len(sample_ohlcv)
    # RSI is between 0 and 100
    assert (rsi.iloc[15:] >= 0).all()
    assert (rsi.iloc[15:] <= 100).all()


def test_compute_rsi_uptrend():
    """Test RSI in strong uptrend."""
    dates = pd.date_range("2024-01-01", periods=50, freq="D")
    # Strong uptrend
    close = pd.Series(np.linspace(100, 150, 50), index=dates)

    rsi = compute_rsi(close, window=14)

    # RSI should be high (>50) in uptrend
    assert rsi.iloc[-10:].mean() > 50


def test_compute_rsi_downtrend():
    """Test RSI in strong downtrend."""
    dates = pd.date_range("2024-01-01", periods=50, freq="D")
    # Strong downtrend
    close = pd.Series(np.linspace(150, 100, 50), index=dates)

    rsi = compute_rsi(close, window=14)

    # RSI should be low (<50) in downtrend
    assert rsi.iloc[-10:].mean() < 50


def test_compute_macd(sample_ohlcv):
    """Test MACD calculation."""
    macd_df = compute_macd(sample_ohlcv["close"])

    assert isinstance(macd_df, pd.DataFrame)
    assert "macd" in macd_df.columns
    assert "macd_signal" in macd_df.columns
    assert "macd_hist" in macd_df.columns
    assert len(macd_df) == len(sample_ohlcv)


def test_compute_macd_histogram_is_difference(sample_ohlcv):
    """Test MACD histogram is difference of MACD and signal."""
    macd_df = compute_macd(sample_ohlcv["close"])

    # Histogram = MACD - Signal
    expected_hist = macd_df["macd"] - macd_df["macd_signal"]
    pd.testing.assert_series_equal(
        macd_df["macd_hist"], expected_hist, check_names=False
    )


def test_compute_bollinger_bands(sample_ohlcv):
    """Test Bollinger Bands calculation."""
    bb_df = compute_bollinger_bands(sample_ohlcv["close"], window=20, num_std=2.0)

    assert isinstance(bb_df, pd.DataFrame)
    assert "bb_middle" in bb_df.columns
    assert "bb_upper" in bb_df.columns
    assert "bb_lower" in bb_df.columns
    assert "bb_width" in bb_df.columns


def test_compute_bollinger_bands_ordering(sample_ohlcv):
    """Test Bollinger Bands ordering (upper > middle > lower)."""
    bb_df = compute_bollinger_bands(sample_ohlcv["close"], window=20)

    valid_idx = bb_df.notna().all(axis=1)
    assert (bb_df.loc[valid_idx, "bb_upper"] >= bb_df.loc[valid_idx, "bb_middle"]).all()
    assert (bb_df.loc[valid_idx, "bb_middle"] >= bb_df.loc[valid_idx, "bb_lower"]).all()


def test_compute_garch_inputs(sample_ohlcv):
    """Test GARCH input features."""
    garch_df = compute_garch_inputs(sample_ohlcv, window=20)

    assert isinstance(garch_df, pd.DataFrame)
    expected_cols = ["ret_mean", "ret_std", "ret_skew", "ret_kurt", "ret_squared", "arch_lag1"]
    for col in expected_cols:
        assert col in garch_df.columns


def test_compute_garch_inputs_arch_lag(sample_ohlcv):
    """Test ARCH lag is shifted squared returns."""
    garch_df = compute_garch_inputs(sample_ohlcv, window=20)

    # ARCH lag1 should be shifted ret_squared
    expected_arch = garch_df["ret_squared"].shift(1)
    pd.testing.assert_series_equal(
        garch_df["arch_lag1"], expected_arch, check_names=False
    )


def test_compute_all_indicators(sample_ohlcv):
    """Test computing all indicators with default config."""
    features = compute_all_indicators(sample_ohlcv)

    assert isinstance(features, pd.DataFrame)
    assert len(features) == len(sample_ohlcv)
    assert features.index.equals(sample_ohlcv.index)

    # Check some expected columns
    assert "return_1" in features.columns
    assert "ema_12" in features.columns
    assert "rsi_14" in features.columns
    assert "macd" in features.columns


def test_compute_all_indicators_custom_config(sample_ohlcv):
    """Test computing indicators with custom config."""
    config = {
        "returns": [1, 5],
        "ema": [12, 26],
        "rsi": [14],
    }

    features = compute_all_indicators(sample_ohlcv, config=config)

    assert "return_1" in features.columns
    assert "return_5" in features.columns
    assert "ema_12" in features.columns
    assert "ema_26" in features.columns
    assert "rsi_14" in features.columns
    # Should not have indicators not in config
    assert "sma_20" not in features.columns


def test_compute_all_indicators_preserves_index(sample_ohlcv):
    """Test that feature index matches input DataFrame."""
    features = compute_all_indicators(sample_ohlcv)

    assert features.index.equals(sample_ohlcv.index)
    assert isinstance(features.index, pd.DatetimeIndex)


def test_indicators_with_small_dataset():
    """Test indicators work with minimal data."""
    dates = pd.date_range("2024-01-01", periods=30, freq="D")
    df = pd.DataFrame(
        {
            "open": 100,
            "high": 101,
            "low": 99,
            "close": 100,
            "volume": 1000,
        },
        index=dates,
    )

    features = compute_all_indicators(df)

    # Should not raise, but many values will be NaN
    assert len(features) == 30
    assert features.isna().any().any()  # Some NaN values expected
