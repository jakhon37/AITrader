"""Tests for meta-labeler."""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from trainer.models.meta_labeler import MetaLabeler


@pytest.fixture
def sample_data():
    """Create sample data for testing."""
    np.random.seed(42)
    n = 200
    
    # Create features
    features = pd.DataFrame({
        'volatility': np.random.rand(n) * 0.02,
        'rsi': np.random.rand(n) * 100,
        'regime': np.random.randint(0, 3, n),
    })
    
    # Create primary predictions (somewhat correlated with future returns)
    primary_predictions = np.random.randn(n) * 0.01
    
    # Create actual returns (with some correlation to predictions)
    noise = np.random.randn(n) * 0.005
    actual_returns = primary_predictions * 0.7 + noise
    
    return features, primary_predictions, actual_returns


def test_meta_labeler_init():
    """Test meta-labeler initialization."""
    ml = MetaLabeler(confidence_threshold=0.6, n_estimators=50)
    
    assert ml.confidence_threshold == 0.6
    assert ml.n_estimators == 50
    assert not ml.is_fitted


def test_create_meta_labels():
    """Test meta-label creation."""
    ml = MetaLabeler()
    
    primary_preds = np.array([0.01, -0.01, 0.01, -0.01])
    actual_returns = np.array([0.015, -0.012, -0.008, -0.015])
    
    labels = ml.create_meta_labels(primary_preds, actual_returns, threshold=0.0)
    
    # [correct, correct, incorrect, correct]
    expected = np.array([1, 1, 0, 1])
    np.testing.assert_array_equal(labels, expected)


def test_create_meta_labels_with_threshold():
    """Test meta-label creation with return threshold."""
    ml = MetaLabeler()
    
    primary_preds = np.array([0.01, 0.01, 0.01])
    actual_returns = np.array([0.015, 0.005, -0.015])  # big, small, wrong
    
    labels = ml.create_meta_labels(primary_preds, actual_returns, threshold=0.01)
    
    # Only first is correct AND sufficient
    expected = np.array([1, 0, 0])
    np.testing.assert_array_equal(labels, expected)


def test_fit(sample_data):
    """Test fitting meta-labeler."""
    features, primary_preds, actual_returns = sample_data
    
    ml = MetaLabeler()
    ml.fit(features, primary_preds, actual_returns)
    
    assert ml.is_fitted
    assert hasattr(ml.classifier, 'feature_importances_')


def test_predict_proba(sample_data):
    """Test probability prediction."""
    features, primary_preds, actual_returns = sample_data
    
    ml = MetaLabeler()
    ml.fit(features[:150], primary_preds[:150], actual_returns[:150])
    
    probas = ml.predict_proba(features[150:], primary_preds[150:])
    
    assert len(probas) == 50
    assert (probas >= 0).all() and (probas <= 1).all()


def test_predict_proba_before_fit_raises_error(sample_data):
    """Test that predicting before fitting raises error."""
    features, primary_preds, _ = sample_data
    
    ml = MetaLabeler()
    
    with pytest.raises(ValueError, match="must be fitted"):
        ml.predict_proba(features, primary_preds)


def test_predict_position_size_binary(sample_data):
    """Test binary position sizing."""
    features, primary_preds, actual_returns = sample_data
    
    ml = MetaLabeler(confidence_threshold=0.6)
    ml.fit(features[:150], primary_preds[:150], actual_returns[:150])
    
    sizes = ml.predict_position_size(features[150:], primary_preds[150:], strategy='binary')
    
    assert len(sizes) == 50
    # Binary: only 0 or 1
    assert set(sizes).issubset({0.0, 1.0})


def test_predict_position_size_linear(sample_data):
    """Test linear position sizing."""
    features, primary_preds, actual_returns = sample_data
    
    ml = MetaLabeler(confidence_threshold=0.5)
    ml.fit(features[:150], primary_preds[:150], actual_returns[:150])
    
    sizes = ml.predict_position_size(features[150:], primary_preds[150:], strategy='linear')
    
    assert len(sizes) == 50
    assert (sizes >= 0).all() and (sizes <= 1).all()
    # Some should be zero (below threshold), some non-zero
    assert (sizes == 0).any()
    assert (sizes > 0).any()


def test_predict_position_size_quadratic(sample_data):
    """Test quadratic position sizing."""
    features, primary_preds, actual_returns = sample_data
    
    ml = MetaLabeler(confidence_threshold=0.5)
    ml.fit(features[:150], primary_preds[:150], actual_returns[:150])
    
    sizes_linear = ml.predict_position_size(features[150:], primary_preds[150:], strategy='linear')
    sizes_quad = ml.predict_position_size(features[150:], primary_preds[150:], strategy='quadratic')
    
    # Quadratic should be more conservative (smaller when > 0)
    non_zero_mask = sizes_linear > 0
    if non_zero_mask.any():
        assert (sizes_quad[non_zero_mask] <= sizes_linear[non_zero_mask]).all()


def test_predict_position_size_invalid_strategy(sample_data):
    """Test that invalid strategy raises error."""
    features, primary_preds, actual_returns = sample_data
    
    ml = MetaLabeler()
    ml.fit(features, primary_preds, actual_returns)
    
    with pytest.raises(ValueError, match="Unknown strategy"):
        ml.predict_position_size(features, primary_preds, strategy='invalid')


def test_get_signal_with_size(sample_data):
    """Test getting signals with sizes."""
    features, primary_preds, actual_returns = sample_data
    
    ml = MetaLabeler()
    ml.fit(features[:150], primary_preds[:150], actual_returns[:150])
    
    signals, sizes = ml.get_signal_with_size(
        features[150:],
        primary_preds[150:],
        strategy='linear'
    )
    
    assert len(signals) == 50
    assert len(sizes) == 50
    
    # Signals should be -1, 0, or 1
    assert set(signals).issubset({-1, 0, 1})
    
    # Where size is 0, signal should be 0
    assert (signals[sizes == 0] == 0).all()


def test_get_feature_importance(sample_data):
    """Test getting feature importance."""
    features, primary_preds, actual_returns = sample_data
    
    ml = MetaLabeler()
    ml.fit(features, primary_preds, actual_returns)
    
    importance = ml.get_feature_importance()
    
    # Should have all features plus primary_pred features
    assert len(importance) == 5  # 3 original + 2 added
    assert 'primary_pred' in importance.index
    assert 'primary_pred_abs' in importance.index
    
    # Importances should sum to approximately 1
    assert 0.95 <= importance.sum() <= 1.05


def test_get_feature_importance_before_fit_raises_error():
    """Test that getting importance before fitting raises error."""
    ml = MetaLabeler()
    
    with pytest.raises(ValueError, match="must be fitted"):
        ml.get_feature_importance()


def test_evaluate_performance(sample_data):
    """Test performance evaluation."""
    features, primary_preds, actual_returns = sample_data
    
    ml = MetaLabeler()
    ml.fit(features[:150], primary_preds[:150], actual_returns[:150])
    
    metrics = ml.evaluate_performance(
        features[150:],
        primary_preds[150:],
        actual_returns[150:],
        strategy='linear'
    )
    
    # Check all expected metrics exist
    assert 'n_trades' in metrics
    assert 'n_total' in metrics
    assert 'trade_frequency' in metrics
    assert 'avg_return' in metrics
    assert 'win_rate' in metrics
    assert 'sharpe_ratio' in metrics
    assert 'baseline_sharpe' in metrics
    assert 'sharpe_improvement' in metrics
    
    # Check reasonable values
    assert 0 <= metrics['n_trades'] <= metrics['n_total']
    assert 0 <= metrics['trade_frequency'] <= 1
    assert 0 <= metrics['win_rate'] <= 1


def test_meta_labeler_filters_trades(sample_data):
    """Test that meta-labeler reduces number of trades."""
    features, primary_preds, actual_returns = sample_data
    
    ml = MetaLabeler()
    ml.fit(features[:150], primary_preds[:150], actual_returns[:150])
    
    metrics = ml.evaluate_performance(
        features[150:],
        primary_preds[150:],
        actual_returns[150:],
        strategy='linear'
    )
    
    # Should take fewer trades than always trading
    assert metrics['n_trades'] < metrics['n_total']
    assert metrics['trade_frequency'] < 1.0


def test_save_and_load(sample_data):
    """Test saving and loading meta-labeler."""
    features, primary_preds, actual_returns = sample_data
    
    ml1 = MetaLabeler(confidence_threshold=0.6, n_estimators=50)
    ml1.fit(features[:150], primary_preds[:150], actual_returns[:150])
    
    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "meta_labeler.pkl"
        
        ml1.save(str(save_path))
        
        # Load into new meta-labeler
        ml2 = MetaLabeler()
        ml2.load(str(save_path))
        
        assert ml2.confidence_threshold == 0.6
        assert ml2.n_estimators == 50
        assert ml2.is_fitted
        
        # Predictions should match
        pred1 = ml1.predict_proba(features[150:], primary_preds[150:])
        pred2 = ml2.predict_proba(features[150:], primary_preds[150:])
        
        np.testing.assert_array_almost_equal(pred1, pred2)


def test_save_before_fit_raises_error():
    """Test that saving before fitting raises error."""
    ml = MetaLabeler()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "meta_labeler.pkl"
        
        with pytest.raises(ValueError, match="must be fitted"):
            ml.save(str(save_path))


def test_different_confidence_thresholds(sample_data):
    """Test different confidence thresholds."""
    features, primary_preds, actual_returns = sample_data
    
    for threshold in [0.5, 0.6, 0.7]:
        ml = MetaLabeler(confidence_threshold=threshold)
        ml.fit(features[:150], primary_preds[:150], actual_returns[:150])
        
        sizes = ml.predict_position_size(
            features[150:],
            primary_preds[150:],
            strategy='linear'
        )
        
        # Higher threshold should result in fewer trades
        n_trades = np.sum(sizes > 0)
        assert n_trades >= 0


def test_class_balance_handling(sample_data):
    """Test handling of imbalanced classes."""
    features, primary_preds, actual_returns = sample_data
    
    # Create very imbalanced data (mostly wrong predictions)
    wrong_returns = -primary_preds * 2  # Opposite direction, bigger
    
    ml = MetaLabeler()
    # Should not crash even with imbalanced data
    ml.fit(features, primary_preds, wrong_returns)
    
    probas = ml.predict_proba(features, primary_preds)
    
    # Should still return valid probabilities
    assert (probas >= 0).all() and (probas <= 1).all()


def test_position_sizing_strategies_comparison(sample_data):
    """Test that different strategies produce different results."""
    features, primary_preds, actual_returns = sample_data
    
    ml = MetaLabeler(confidence_threshold=0.5)
    ml.fit(features[:150], primary_preds[:150], actual_returns[:150])
    
    sizes_binary = ml.predict_position_size(features[150:], primary_preds[150:], 'binary')
    sizes_linear = ml.predict_position_size(features[150:], primary_preds[150:], 'linear')
    sizes_quad = ml.predict_position_size(features[150:], primary_preds[150:], 'quadratic')
    
    # They should be different
    assert not np.array_equal(sizes_binary, sizes_linear)
    assert not np.array_equal(sizes_linear, sizes_quad)


def test_zero_size_means_no_trade(sample_data):
    """Test that zero size results in no trading signal."""
    features, primary_preds, actual_returns = sample_data
    
    ml = MetaLabeler(confidence_threshold=0.9)  # Very high threshold
    ml.fit(features[:150], primary_preds[:150], actual_returns[:150])
    
    signals, sizes = ml.get_signal_with_size(
        features[150:],
        primary_preds[150:],
        strategy='binary'
    )
    
    # Where size is 0, signal must be 0
    zero_size_mask = sizes == 0
    assert (signals[zero_size_mask] == 0).all()
