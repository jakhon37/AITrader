"""Tests for ensemble model."""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from models.ensemble import EnsembleModel


class MockModel:
    """Mock model for testing."""
    
    def __init__(self, predictions: np.ndarray) -> None:
        self.predictions = predictions
        self.call_count = 0
    
    def predict(self, X: pd.DataFrame | np.ndarray, **kwargs) -> np.ndarray:
        self.call_count += 1
        return self.predictions.copy()


@pytest.fixture
def sample_data():
    """Create sample data for testing."""
    np.random.seed(42)
    n = 100
    n_features = 5
    
    X = pd.DataFrame(np.random.randn(n, n_features))
    return X


@pytest.fixture
def mock_models():
    """Create mock models with different predictions."""
    np.random.seed(42)
    n = 100
    
    # Create 3 models with slightly different predictions
    model1 = MockModel(np.random.randn(n) * 0.01 + 0.001)
    model2 = MockModel(np.random.randn(n) * 0.01 - 0.001)
    model3 = MockModel(np.random.randn(n) * 0.01)
    
    return [model1, model2, model3]


def test_ensemble_init_with_equal_weights(mock_models):
    """Test ensemble initialization with equal weights."""
    ensemble = EnsembleModel(models=mock_models)
    
    assert len(ensemble.models) == 3
    assert len(ensemble.weights) == 3
    np.testing.assert_array_almost_equal(ensemble.weights, [1/3, 1/3, 1/3])


def test_ensemble_init_with_custom_weights(mock_models):
    """Test ensemble initialization with custom weights."""
    weights = [0.5, 0.3, 0.2]
    ensemble = EnsembleModel(models=mock_models, weights=weights)
    
    np.testing.assert_array_almost_equal(ensemble.weights, weights)


def test_ensemble_init_invalid_weights(mock_models):
    """Test that invalid weights raise errors."""
    # Wrong number of weights
    with pytest.raises(ValueError, match="Number of weights"):
        EnsembleModel(models=mock_models, weights=[0.5, 0.5])
    
    # Weights don't sum to 1
    with pytest.raises(ValueError, match="sum to 1"):
        EnsembleModel(models=mock_models, weights=[0.5, 0.3, 0.3])


def test_add_model():
    """Test adding models to ensemble."""
    ensemble = EnsembleModel()
    assert len(ensemble.models) == 0
    
    model = MockModel(np.array([1, 2, 3]))
    ensemble.add_model(model)
    
    assert len(ensemble.models) == 1
    assert ensemble.weights[0] == 1.0


def test_add_model_with_weight(mock_models):
    """Test adding model with custom weight."""
    ensemble = EnsembleModel(models=mock_models[:2])
    
    # Add third model with specific weight
    ensemble.add_model(mock_models[2], weight=0.5)
    
    # Weights should be renormalized
    assert len(ensemble.weights) == 3
    assert np.isclose(ensemble.weights.sum(), 1.0)


def test_add_model_without_predict_raises_error():
    """Test that adding model without predict() raises error."""
    ensemble = EnsembleModel()
    
    class BadModel:
        pass
    
    with pytest.raises(ValueError, match="predict"):
        ensemble.add_model(BadModel())


def test_remove_model(mock_models):
    """Test removing models from ensemble."""
    ensemble = EnsembleModel(models=mock_models)
    assert len(ensemble.models) == 3
    
    ensemble.remove_model(1)
    
    assert len(ensemble.models) == 2
    assert len(ensemble.weights) == 2
    assert np.isclose(ensemble.weights.sum(), 1.0)


def test_remove_model_invalid_index(mock_models):
    """Test that invalid index raises error."""
    ensemble = EnsembleModel(models=mock_models)
    
    with pytest.raises(ValueError, match="Invalid model index"):
        ensemble.remove_model(5)


def test_predict_weighted_average(mock_models, sample_data):
    """Test weighted average prediction."""
    weights = [0.5, 0.3, 0.2]
    ensemble = EnsembleModel(models=mock_models, weights=weights, strategy='weighted_average')
    
    predictions = ensemble.predict(sample_data)
    
    # Should call each model once
    assert all(m.call_count == 1 for m in mock_models)
    
    # Should return predictions
    assert len(predictions) == 100
    assert not np.isnan(predictions).any()


def test_predict_simple_average(mock_models, sample_data):
    """Test simple average prediction."""
    ensemble = EnsembleModel(models=mock_models, strategy='simple_average')
    
    predictions = ensemble.predict(sample_data)
    
    # Manually calculate expected
    expected = (mock_models[0].predictions + mock_models[1].predictions + 
                mock_models[2].predictions) / 3
    
    np.testing.assert_array_almost_equal(predictions, expected)


def test_predict_median(mock_models, sample_data):
    """Test median prediction."""
    ensemble = EnsembleModel(models=mock_models, strategy='median')
    
    predictions = ensemble.predict(sample_data)
    
    # Should return median
    all_preds = np.array([m.predictions for m in mock_models])
    expected = np.median(all_preds, axis=0)
    
    np.testing.assert_array_almost_equal(predictions, expected)


def test_predict_voting(mock_models, sample_data):
    """Test voting prediction."""
    ensemble = EnsembleModel(models=mock_models, strategy='voting')
    
    predictions = ensemble.predict(sample_data)
    
    # Voting converts to binary and averages
    assert len(predictions) == 100
    assert (predictions >= 0).all() and (predictions <= 1).all()


def test_predict_dynamic(mock_models, sample_data):
    """Test dynamic weighting."""
    ensemble = EnsembleModel(models=mock_models, strategy='dynamic')
    
    # Without error history, should use equal weights
    predictions1 = ensemble.predict(sample_data)
    
    # Add error history (model 0 is best)
    actual = np.zeros(100)
    ensemble.update_errors(
        [m.predictions for m in mock_models],
        actual
    )
    
    # Now predictions should weight model 0 more heavily
    predictions2 = ensemble.predict(sample_data)
    
    weights = ensemble.get_model_weights()
    # Model with lowest error should have highest weight
    assert weights[0] > weights[1]


def test_predict_empty_ensemble_raises_error(sample_data):
    """Test that predicting with no models raises error."""
    ensemble = EnsembleModel()
    
    with pytest.raises(ValueError, match="No models"):
        ensemble.predict(sample_data)


def test_predict_with_different_lengths(sample_data):
    """Test handling models that return different length predictions."""
    model1 = MockModel(np.random.randn(100))
    model2 = MockModel(np.random.randn(95))  # Different length
    model3 = MockModel(np.random.randn(98))
    
    ensemble = EnsembleModel(models=[model1, model2, model3])
    
    predictions = ensemble.predict(sample_data)
    
    # Should return minimum length
    assert len(predictions) == 95


def test_update_errors(mock_models):
    """Test updating error history."""
    ensemble = EnsembleModel(models=mock_models, strategy='dynamic')
    
    predictions = [m.predictions for m in mock_models]
    actual = np.zeros(100)
    
    ensemble.update_errors(predictions, actual)
    
    # Should have error history
    for errors in ensemble.recent_errors:
        assert len(errors) == 100


def test_update_errors_invalid_length(mock_models):
    """Test that wrong number of predictions raises error."""
    ensemble = EnsembleModel(models=mock_models)
    
    with pytest.raises(ValueError, match="Number of predictions"):
        ensemble.update_errors([np.array([1, 2])], np.array([1, 2]))


def test_get_model_weights(mock_models):
    """Test getting model weights."""
    weights = [0.5, 0.3, 0.2]
    ensemble = EnsembleModel(models=mock_models, weights=weights)
    
    model_weights = ensemble.get_model_weights()
    
    assert len(model_weights) == 3
    assert model_weights[0] == 0.5
    assert model_weights[1] == 0.3
    assert model_weights[2] == 0.2


def test_get_predictions_with_confidence(mock_models, sample_data):
    """Test getting predictions with confidence scores."""
    ensemble = EnsembleModel(models=mock_models)
    
    predictions, confidence = ensemble.get_predictions_with_confidence(sample_data)
    
    assert len(predictions) == 100
    assert len(confidence) == 100
    assert (confidence >= 0).all() and (confidence <= 1).all()
    # Higher agreement should mean higher confidence
    assert confidence.max() > 0.5


def test_save_and_load(mock_models):
    """Test saving and loading ensemble config."""
    ensemble = EnsembleModel(models=mock_models, weights=[0.5, 0.3, 0.2])
    
    # Add some error history
    ensemble.recent_errors = [[1, 2, 3], [4, 5], [6]]
    
    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "ensemble.json"
        
        ensemble.save(str(save_path))
        
        # Load into new ensemble
        new_ensemble = EnsembleModel()
        new_ensemble.load(str(save_path))
        
        assert new_ensemble.strategy == 'weighted_average'
        np.testing.assert_array_almost_equal(new_ensemble.weights, [0.5, 0.3, 0.2])
        assert new_ensemble.recent_errors == [[1, 2, 3], [4, 5], [6]]


def test_get_diversity_score(mock_models, sample_data):
    """Test calculating diversity score."""
    ensemble = EnsembleModel(models=mock_models)
    
    diversity = ensemble.get_diversity_score(sample_data)
    
    # Should return a value between 0 and 2
    assert 0 <= diversity <= 2


def test_get_diversity_score_single_model(sample_data):
    """Test diversity score with single model."""
    model = MockModel(np.random.randn(100))
    ensemble = EnsembleModel(models=[model])
    
    diversity = ensemble.get_diversity_score(sample_data)
    
    # Single model has no diversity
    assert diversity == 0.0


def test_dynamic_weighting_window(mock_models):
    """Test that dynamic weighting respects window size."""
    ensemble = EnsembleModel(models=mock_models, strategy='dynamic', dynamic_window=10)
    
    # Add lots of errors
    for _ in range(5):
        predictions = [m.predictions for m in mock_models]
        actual = np.zeros(100)
        ensemble.update_errors(predictions, actual)
    
    # Should keep only recent window * 2
    for errors in ensemble.recent_errors:
        assert len(errors) <= 20  # dynamic_window * 2


def test_multiple_strategies(mock_models, sample_data):
    """Test that all strategies produce valid output."""
    strategies = ['weighted_average', 'simple_average', 'median', 'voting', 'dynamic']
    
    for strategy in strategies:
        ensemble = EnsembleModel(models=mock_models, strategy=strategy)
        predictions = ensemble.predict(sample_data)
        
        assert len(predictions) == 100
        assert not np.isnan(predictions).any()


def test_predict_with_kwargs(sample_data):
    """Test that kwargs are passed to models."""
    class KwargsModel:
        def predict(self, X, seq_length=20):
            self.seq_length = seq_length
            return np.random.randn(len(X) - seq_length + 1)
    
    model1 = KwargsModel()
    model2 = KwargsModel()
    
    ensemble = EnsembleModel(models=[model1, model2])
    
    predictions = ensemble.predict(sample_data, seq_length=30)
    
    assert model1.seq_length == 30
    assert model2.seq_length == 30
