"""Tests for FeatureEngine."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from features.feature_engine import FeatureEngine


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


def test_feature_engine_init_default():
    """Test FeatureEngine initialization with default config."""
    engine = FeatureEngine()

    assert engine.config is not None
    assert "technical_indicators" in engine.config


def test_feature_engine_init_custom_config():
    """Test FeatureEngine with custom config."""
    config = {
        "technical_indicators": {
            "returns": [1, 5],
            "ema": [12, 26],
        }
    }

    engine = FeatureEngine(config=config)

    assert engine.config == config


def test_compute_features_returns_dataframe(sample_ohlcv):
    """Test compute_features returns DataFrame."""
    engine = FeatureEngine()
    features = engine.compute_features(sample_ohlcv)

    assert isinstance(features, pd.DataFrame)
    assert len(features) == len(sample_ohlcv)
    assert features.index.equals(sample_ohlcv.index)


def test_compute_features_has_expected_columns(sample_ohlcv):
    """Test computed features have expected columns."""
    engine = FeatureEngine()
    features = engine.compute_features(sample_ohlcv)

    # Check some expected columns from default config
    expected = ["return_1", "ema_12", "rsi_14", "macd"]
    for col in expected:
        assert col in features.columns


def test_compute_features_caching(sample_ohlcv):
    """Test feature caching works."""
    engine = FeatureEngine()

    # First call
    features1 = engine.compute_features(sample_ohlcv, use_cache=True)

    # Second call should return cached result
    features2 = engine.compute_features(sample_ohlcv, use_cache=True)

    pd.testing.assert_frame_equal(features1, features2)


def test_compute_features_no_cache(sample_ohlcv):
    """Test disabling cache."""
    engine = FeatureEngine()

    features1 = engine.compute_features(sample_ohlcv, use_cache=False)
    features2 = engine.compute_features(sample_ohlcv, use_cache=False)

    # Results should be the same even without cache
    pd.testing.assert_frame_equal(features1, features2)


def test_clear_cache(sample_ohlcv):
    """Test clearing cache."""
    engine = FeatureEngine()

    engine.compute_features(sample_ohlcv, use_cache=True)
    assert len(engine._cache) > 0

    engine.clear_cache()
    assert len(engine._cache) == 0


def test_compute_features_at_time(sample_ohlcv):
    """Test computing features at specific time."""
    engine = FeatureEngine()

    time = sample_ohlcv.index[50]
    features_at_t = engine.compute_features_at_time(sample_ohlcv, time)

    assert isinstance(features_at_t, pd.Series)
    assert features_at_t.name == time


def test_compute_features_at_time_invalid_time(sample_ohlcv):
    """Test error when time not in index."""
    engine = FeatureEngine()

    invalid_time = pd.Timestamp("2025-01-01")

    with pytest.raises(ValueError, match="not in DataFrame index"):
        engine.compute_features_at_time(sample_ohlcv, invalid_time)


def test_compute_features_rolling(sample_ohlcv):
    """Test rolling feature computation."""
    engine = FeatureEngine()

    window = 30
    features = engine.compute_features_rolling(sample_ohlcv, window=window)

    assert isinstance(features, pd.DataFrame)
    assert len(features) == len(sample_ohlcv) - window + 1
    assert features.index.equals(sample_ohlcv.index[window - 1 :])


def test_compute_features_rolling_small_window(sample_ohlcv):
    """Test rolling with window too large."""
    engine = FeatureEngine()

    with pytest.raises(ValueError, match="DataFrame length.*< window"):
        engine.compute_features_rolling(sample_ohlcv, window=200)


def test_validate_no_leakage(sample_ohlcv):
    """Test no future leakage validation."""
    engine = FeatureEngine()

    features = engine.compute_features(sample_ohlcv)
    time = sample_ohlcv.index[50]

    # Should not raise
    assert engine.validate_no_leakage(sample_ohlcv, features, time) is True


def test_validate_no_leakage_detects_leakage(sample_ohlcv):
    """Test that leakage is detected if present."""
    engine = FeatureEngine()

    features = engine.compute_features(sample_ohlcv)

    # Manually inject future data into features
    time = sample_ohlcv.index[50]
    features.loc[time, "return_1"] = sample_ohlcv.loc[sample_ohlcv.index[51], "close"]

    # Should raise AssertionError
    with pytest.raises(AssertionError, match="Future leakage detected"):
        engine.validate_no_leakage(sample_ohlcv, features, time)


def test_get_feature_names():
    """Test getting feature names."""
    engine = FeatureEngine()

    feature_names = engine.get_feature_names()

    assert isinstance(feature_names, list)
    assert len(feature_names) > 0
    assert "return_1" in feature_names


def test_get_feature_names_custom_config():
    """Test feature names with custom config."""
    config = {
        "technical_indicators": {
            "returns": [1],
            "ema": [12],
        }
    }

    engine = FeatureEngine(config=config)
    feature_names = engine.get_feature_names()

    assert "return_1" in feature_names
    assert "ema_12" in feature_names
    # Should not have features not in config
    assert "rsi_14" not in feature_names


def test_validate_input_not_dataframe():
    """Test validation rejects non-DataFrame."""
    engine = FeatureEngine()

    with pytest.raises(ValueError, match="must be a pandas DataFrame"):
        engine.compute_features([1, 2, 3])  # type: ignore


def test_validate_input_no_datetime_index():
    """Test validation requires DatetimeIndex."""
    engine = FeatureEngine()

    df = pd.DataFrame(
        {
            "open": [100, 101],
            "high": [102, 103],
            "low": [99, 100],
            "close": [101, 102],
        }
    )

    with pytest.raises(ValueError, match="must have DatetimeIndex"):
        engine.compute_features(df)


def test_validate_input_missing_columns():
    """Test validation checks required columns."""
    engine = FeatureEngine()

    df = pd.DataFrame(
        {"close": [100, 101]}, index=pd.date_range("2024-01-01", periods=2, freq="D")
    )

    with pytest.raises(ValueError, match="Missing required columns"):
        engine.compute_features(df)


def test_validate_input_empty_dataframe():
    """Test validation rejects empty DataFrame."""
    engine = FeatureEngine()

    df = pd.DataFrame(
        {
            "open": [],
            "high": [],
            "low": [],
            "close": [],
        },
        index=pd.DatetimeIndex([]),
    )

    with pytest.raises(ValueError, match="DataFrame is empty"):
        engine.compute_features(df)


def test_minimal_config(sample_ohlcv):
    """Test with minimal feature config."""
    config = {
        "technical_indicators": {
            "returns": [1],
        }
    }

    engine = FeatureEngine(config=config)
    features = engine.compute_features(sample_ohlcv)

    assert "return_1" in features.columns
    assert "log_return_1" in features.columns


def test_point_in_time_guarantee(sample_ohlcv):
    """Test that features at time T only use data up to T."""
    engine = FeatureEngine()

    time_50 = sample_ohlcv.index[50]
    time_60 = sample_ohlcv.index[60]

    # Compute features at different times
    features_50 = engine.compute_features_at_time(sample_ohlcv, time_50)
    features_60 = engine.compute_features_at_time(sample_ohlcv, time_60)

    # Features at time 50 should not change when we add more data
    df_past_50 = sample_ohlcv.loc[:time_50]
    features_past_50 = engine.compute_features(df_past_50, use_cache=False)

    pd.testing.assert_series_equal(
        features_50,
        features_past_50.loc[time_50],
        check_names=False,
    )
