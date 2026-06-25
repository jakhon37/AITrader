"""End-to-end integration test for complete backtest pipeline."""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from backtest.engine import BacktestConfig, BacktestEngine
from backtest.metrics import calculate_metrics
from backtest.walk_forward import WalkForwardConfig, WalkForwardValidator
from data.loaders.csv_loader import load_ohlcv_csv
from trainer.feature_engine import FeatureEngine
from trainer.models.garch_gru import GARCHGRUModel
from trainer.models.lstm_transformer import LSTMTransformerModel
from trainer.models.model_registry import ModelRegistry


def test_full_backtest_pipeline():
    """Test complete pipeline: data → features → model → backtest → metrics."""
    # Load data
    data_path = Path("data/raw/eurusd_daily.csv")
    if not data_path.exists():
        pytest.skip("EUR/USD data not available")

    data = load_ohlcv_csv(data_path)
    assert len(data) > 100

    # Compute features
    feature_engine = FeatureEngine()
    features = feature_engine.compute_features(data)
    features = features.dropna()
    assert len(features) > 50

    # Simple signals for testing (based on returns)
    signals = pd.Series(0, index=features.index)
    returns = data["close"].pct_change()
    signals[returns.loc[features.index] > 0] = 1
    signals[returns.loc[features.index] < 0] = -1

    # Align data with signals
    data = data.loc[signals.index]

    # Run backtest
    config = BacktestConfig(initial_capital=10000.0)
    engine = BacktestEngine(config)
    result = engine.run(data, signals)

    # Calculate metrics
    metrics = calculate_metrics(result)

    # Assertions
    assert len(result.trades) > 0, "Should execute at least one trade"
    assert len(result.equity_curve) == len(data)
    assert metrics.total_trades == len(result.trades)
    assert abs(metrics.total_return) < 10.0  # Sanity check


def test_walk_forward_validation():
    """Test walk-forward validation."""
    data_path = Path("data/raw/eurusd_daily.csv")
    if not data_path.exists():
        pytest.skip("EUR/USD data not available")

    data = load_ohlcv_csv(data_path)

    # Simple signals
    signals = pd.Series(1, index=data.index)

    # Walk-forward config
    wf_config = WalkForwardConfig(
        train_period=100, test_period=50, step_size=50
    )

    validator = WalkForwardValidator(wf_config=wf_config)
    result = validator.run(data, signals)

    # Assertions
    assert len(result.windows) > 0
    assert result.summary_metrics["num_windows"] == len(result.windows)

    for window in result.windows:
        assert window.result is not None
        assert window.metrics is not None
        assert window.train_size == 100
        assert window.test_size == 50


def test_model_loading_and_prediction():
    """Test loading trained models from registry."""
    registry_path = Path("models/registry")
    if not registry_path.exists():
        pytest.skip("Model registry not available")

    registry = ModelRegistry(base_path=str(registry_path))

    # Check if we have models
    if "lstm_transformer" not in registry.index["models"]:
        pytest.skip("No LSTM-Transformer models in registry")

    # Get latest model
    versions = registry.index["models"]["lstm_transformer"]
    if not versions:
        pytest.skip("No LSTM-Transformer versions found")

    version = versions[-1]

    # Load model
    model = LSTMTransformerModel()
    model_path = registry.get_model_path("lstm_transformer", version)
    model.load(model_path)

    # Load some data for prediction
    data_path = Path("data/raw/eurusd_daily.csv")
    if not data_path.exists():
        pytest.skip("EUR/USD data not available")

    data = load_ohlcv_csv(data_path)
    feature_engine = FeatureEngine()
    features = feature_engine.compute_features(data)
    features = features.dropna().head(100)  # Use first 100 valid rows

    # Predict
    predictions = model.predict(features)

    # Assertions
    assert predictions is not None
    assert len(predictions) > 0
    assert len(predictions) <= len(features)


def test_backtest_with_trained_model():
    """Test full backtest with a trained model."""
    # Load model
    registry_path = Path("models/registry")
    if not registry_path.exists():
        pytest.skip("Model registry not available")

    registry = ModelRegistry(base_path=str(registry_path))

    if "lstm_transformer" not in registry.index["models"]:
        pytest.skip("No LSTM-Transformer models")

    versions = registry.index["models"]["lstm_transformer"]
    if not versions:
        pytest.skip("No versions found")

    version = versions[-1]

    # Load data
    data_path = Path("data/raw/eurusd_daily.csv")
    if not data_path.exists():
        pytest.skip("EUR/USD data not available")

    data = load_ohlcv_csv(data_path)

    # Compute features
    feature_engine = FeatureEngine()
    features = feature_engine.compute_features(data)
    features = features.dropna()

    # Load model and predict
    model = LSTMTransformerModel()
    model_path = registry.get_model_path("lstm_transformer", version)
    model.load(model_path)
    predictions = model.predict(features)

    # Convert to signals
    if len(predictions) != len(features):
        predictions = pd.Series(predictions, index=features.index[-len(predictions) :])
    else:
        predictions = pd.Series(predictions, index=features.index)

    signals = pd.Series(0, index=predictions.index)
    signals[predictions > 0] = 1
    signals[predictions < 0] = -1

    # Align data
    data = data.loc[signals.index]

    # Run backtest
    config = BacktestConfig()
    engine = BacktestEngine(config)
    result = engine.run(data, signals)
    metrics = calculate_metrics(result)

    # Assertions
    assert result is not None
    assert metrics is not None
    assert len(result.equity_curve) > 0


def test_backtest_edge_cases():
    """Test edge cases in backtesting."""
    # Create minimal data
    dates = pd.date_range("2024-01-01", periods=10, freq="D")
    data = pd.DataFrame(
        {"close": [100 + i for i in range(10)], "volume": [1000] * 10},
        index=dates,
    )

    # No signals (all zeros)
    signals = pd.Series(0, index=dates)
    engine = BacktestEngine()
    result = engine.run(data, signals)
    assert len(result.trades) == 0

    # Single trade
    signals = pd.Series([1] * 5 + [0] * 5, index=dates)
    result = engine.run(data, signals)
    assert len(result.trades) == 1

    # Alternating signals
    signals = pd.Series([1, -1] * 5, index=dates)
    result = engine.run(data, signals)
    assert len(result.trades) >= 2
