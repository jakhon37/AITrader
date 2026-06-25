"""Tests for RegimeDetector."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from trainer.regime_detector import RegimeDetector, detect_regimes


@pytest.fixture
def sample_ohlcv() -> pd.DataFrame:
    """Create sample OHLCV data with distinct regimes."""
    dates = pd.date_range("2024-01-01", periods=200, freq="D")
    np.random.seed(42)

    # Create data with 3 distinct regimes
    close = np.concatenate(
        [
            100 + np.cumsum(np.random.randn(70) * 0.5 + 0.3),  # Bullish
            130 + np.random.randn(60) * 0.2,  # Ranging
            130 + np.cumsum(np.random.randn(70) * 0.5 - 0.3),  # Bearish
        ]
    )

    high = close + np.abs(np.random.randn(200) * 0.3)
    low = close - np.abs(np.random.randn(200) * 0.3)
    open_ = close + np.random.randn(200) * 0.2

    return pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": np.random.randint(1000, 10000, 200),
        },
        index=dates,
    )


def test_regime_detector_init():
    """Test RegimeDetector initialization."""
    detector = RegimeDetector(n_regimes=3)

    assert detector.n_regimes == 3
    assert detector.model is None
    assert not detector._is_fitted


def test_regime_detector_init_custom_params():
    """Test initialization with custom parameters."""
    detector = RegimeDetector(
        n_regimes=4,
        covariance_type="diag",
        n_iter=200,
        random_state=42,
    )

    assert detector.n_regimes == 4
    assert detector.covariance_type == "diag"
    assert detector.n_iter == 200
    assert detector.random_state == 42


def test_regime_detector_fit(sample_ohlcv):
    """Test fitting HMM on data."""
    detector = RegimeDetector(n_regimes=3, random_state=42)
    detector.fit(sample_ohlcv)

    assert detector._is_fitted
    assert detector.model is not None


def test_regime_detector_predict(sample_ohlcv):
    """Test regime prediction."""
    detector = RegimeDetector(n_regimes=3, random_state=42)
    detector.fit(sample_ohlcv)

    regimes = detector.predict(sample_ohlcv)

    assert isinstance(regimes, np.ndarray)
    assert len(regimes) > 0
    assert regimes.min() >= 0
    assert regimes.max() < 3


def test_regime_detector_predict_before_fit(sample_ohlcv):
    """Test that predict raises error if not fitted."""
    detector = RegimeDetector(n_regimes=3)

    with pytest.raises(ValueError, match="Model must be fitted"):
        detector.predict(sample_ohlcv)


def test_regime_detector_predict_proba(sample_ohlcv):
    """Test regime probability prediction."""
    detector = RegimeDetector(n_regimes=3, random_state=42)
    detector.fit(sample_ohlcv)

    proba = detector.predict_proba(sample_ohlcv)

    assert isinstance(proba, np.ndarray)
    assert proba.shape[1] == 3  # n_regimes
    assert np.allclose(proba.sum(axis=1), 1.0)  # Probabilities sum to 1
    assert (proba >= 0).all() and (proba <= 1).all()


def test_regime_detector_predict_proba_before_fit(sample_ohlcv):
    """Test that predict_proba raises error if not fitted."""
    detector = RegimeDetector(n_regimes=3)

    with pytest.raises(ValueError, match="Model must be fitted"):
        detector.predict_proba(sample_ohlcv)


def test_regime_detector_detects_multiple_regimes(sample_ohlcv):
    """Test that detector finds multiple regimes."""
    detector = RegimeDetector(n_regimes=3, random_state=42)
    detector.fit(sample_ohlcv)
    regimes = detector.predict(sample_ohlcv)

    unique_regimes = np.unique(regimes)
    # Should detect at least 2 regimes in varied data
    assert len(unique_regimes) >= 2


def test_get_regime_stats(sample_ohlcv):
    """Test computing regime statistics."""
    detector = RegimeDetector(n_regimes=3, random_state=42)
    detector.fit(sample_ohlcv)
    regimes = detector.predict(sample_ohlcv)

    stats = detector.get_regime_stats(sample_ohlcv, regimes)

    assert isinstance(stats, pd.DataFrame)
    assert "regime" in stats.columns
    assert "count" in stats.columns
    assert "mean_return" in stats.columns
    assert "std_return" in stats.columns
    assert "sharpe" in stats.columns
    assert len(stats) <= 3  # At most n_regimes


def test_get_regime_stats_values(sample_ohlcv):
    """Test regime statistics have reasonable values."""
    detector = RegimeDetector(n_regimes=3, random_state=42)
    detector.fit(sample_ohlcv)
    regimes = detector.predict(sample_ohlcv)

    stats = detector.get_regime_stats(sample_ohlcv, regimes)

    # All regimes should have some observations
    assert (stats["count"] > 0).all()
    # Standard deviation should be positive or NaN (for single observation regimes)
    assert ((stats["std_return"] > 0) | stats["std_return"].isna()).all()


def test_label_regimes(sample_ohlcv):
    """Test regime labeling."""
    detector = RegimeDetector(n_regimes=3, random_state=42)
    detector.fit(sample_ohlcv)
    regimes = detector.predict(sample_ohlcv)

    labels = detector.label_regimes(sample_ohlcv, regimes)

    assert isinstance(labels, dict)
    assert len(labels) <= 3
    # Check labels are reasonable strings
    valid_labels = {
        "bullish_volatile",
        "bullish_stable",
        "bearish_volatile",
        "bearish_stable",
        "ranging_volatile",
        "ranging_stable",
    }
    for label in labels.values():
        assert label in valid_labels


def test_regime_detector_with_custom_features():
    """Test using custom features."""
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    df = pd.DataFrame(
        {
            "open": 100,
            "high": 101,
            "low": 99,
            "close": 100,
            "feature1": np.random.randn(100),
            "feature2": np.random.randn(100),
        },
        index=dates,
    )

    detector = RegimeDetector(n_regimes=2, random_state=42)
    detector.fit(df, features=["feature1", "feature2"])

    regimes = detector.predict(df, features=["feature1", "feature2"])

    assert len(regimes) == 100


def test_detect_regimes_convenience_function(sample_ohlcv):
    """Test convenience function for regime detection."""
    regimes = detect_regimes(sample_ohlcv, n_regimes=3, random_state=42)

    assert isinstance(regimes, pd.Series)
    assert len(regimes) == len(sample_ohlcv)
    assert regimes.index.equals(sample_ohlcv.index)


def test_detect_regimes_has_nan_for_warmup(sample_ohlcv):
    """Test that initial values are NaN due to feature calculation."""
    regimes = detect_regimes(sample_ohlcv, n_regimes=3, random_state=42)

    # Should have some NaN at the beginning
    assert regimes.isna().any()
    # But should have valid values later
    assert regimes.notna().any()


def test_regime_detector_reproducibility(sample_ohlcv):
    """Test that results are reproducible with same random_state."""
    detector1 = RegimeDetector(n_regimes=3, random_state=42)
    detector1.fit(sample_ohlcv)
    regimes1 = detector1.predict(sample_ohlcv)

    detector2 = RegimeDetector(n_regimes=3, random_state=42)
    detector2.fit(sample_ohlcv)
    regimes2 = detector2.predict(sample_ohlcv)

    np.testing.assert_array_equal(regimes1, regimes2)


def test_regime_detector_handles_nan():
    """Test that detector handles NaN values in features."""
    dates = pd.date_range("2024-01-01", periods=50, freq="D")
    df = pd.DataFrame(
        {
            "open": np.random.randn(50) + 100,
            "high": np.random.randn(50) + 101,
            "low": np.random.randn(50) + 99,
            "close": np.random.randn(50) + 100,
        },
        index=dates,
    )

    detector = RegimeDetector(n_regimes=2, random_state=42)

    # Should not raise even with NaN from feature calculation
    detector.fit(df)
    regimes = detector.predict(df)

    assert len(regimes) > 0


def test_different_covariance_types(sample_ohlcv):
    """Test different covariance matrix types."""
    for cov_type in ["spherical", "diag", "full"]:
        detector = RegimeDetector(
            n_regimes=2, covariance_type=cov_type, random_state=42
        )
        detector.fit(sample_ohlcv)
        regimes = detector.predict(sample_ohlcv)

        assert len(regimes) > 0


def test_regime_detector_with_different_n_regimes():
    """Test with different numbers of regimes."""
    dates = pd.date_range("2024-01-01", periods=200, freq="D")
    np.random.seed(42)
    df = pd.DataFrame(
        {
            "open": 100,
            "high": 101,
            "low": 99,
            "close": 100 + np.cumsum(np.random.randn(200) * 0.5),
        },
        index=dates,
    )

    # Test with 2-3 regimes using diagonal covariance (more stable)
    for n in [2, 3]:
        detector = RegimeDetector(n_regimes=n, covariance_type="diag", random_state=42)
        detector.fit(df)
        regimes = detector.predict(df)

        assert regimes.max() < n
        assert regimes.min() >= 0
        # Check that we actually detect regimes
        assert len(regimes) > 0
