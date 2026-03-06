"""Tests for GARCH-GRU model."""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import torch

from models.garch_gru import GARCHGRU, GARCHGRUModel


@pytest.fixture
def sample_returns():
    """Create sample return series."""
    np.random.seed(42)
    n = 200
    
    # Generate returns with volatility clustering
    returns = np.random.randn(n) * 0.01
    dates = pd.date_range('2024-01-01', periods=n, freq='D')
    
    return pd.Series(returns, index=dates)


def test_garchgru_module_init():
    """Test GARCHGRU module initialization."""
    model = GARCHGRU(input_size=2, hidden_size=32, num_layers=1)
    
    assert model.input_size == 2
    assert model.hidden_size == 32
    assert model.num_layers == 1
    assert model.output_size == 1


def test_garchgru_forward_pass():
    """Test forward pass through model."""
    model = GARCHGRU(input_size=2, hidden_size=32, num_layers=1)
    
    # Create dummy input: (batch=4, seq_len=10, features=2)
    x = torch.randn(4, 10, 2)
    
    output = model(x)
    
    assert output.shape == (4, 1)
    assert not torch.isnan(output).any()


def test_garchgru_model_init():
    """Test GARCHGRUModel wrapper initialization."""
    model = GARCHGRUModel(hidden_size=32, num_layers=1)
    
    assert model.hidden_size == 32
    assert model.num_layers == 1
    assert model.model is None  # Not fitted yet


def test_fit_garch(sample_returns):
    """Test GARCH fitting."""
    model = GARCHGRUModel(hidden_size=16, num_layers=1)
    
    volatility = model.fit_garch(sample_returns)
    
    assert len(volatility) == len(sample_returns)
    assert (volatility > 0).all()
    assert not np.isnan(volatility).any()


def test_prepare_sequences():
    """Test sequence preparation."""
    model = GARCHGRUModel(hidden_size=16, num_layers=1)
    
    features = np.random.randn(100, 2)
    targets = np.random.randn(100)
    
    X, y = model.prepare_sequences(features, targets, seq_length=10)
    
    assert X.shape == (90, 10, 2)  # 100 - 10 = 90 sequences
    assert y.shape == (90, 1)
    assert isinstance(X, torch.Tensor)
    assert isinstance(y, torch.Tensor)


def test_fit_basic(sample_returns):
    """Test basic model fitting."""
    model = GARCHGRUModel(hidden_size=16, num_layers=1)
    
    history = model.fit(
        sample_returns,
        epochs=5,
        batch_size=16,
        seq_length=10,
        verbose=False
    )
    
    assert 'train_loss' in history
    assert 'val_loss' in history
    assert len(history['train_loss']) == 5
    assert model.model is not None
    assert model.feature_mean is not None
    assert model.feature_std is not None


def test_fit_reduces_loss(sample_returns):
    """Test that training reduces loss."""
    model = GARCHGRUModel(hidden_size=32, num_layers=1)
    
    history = model.fit(
        sample_returns,
        epochs=20,
        batch_size=16,
        verbose=False
    )
    
    # Loss should generally decrease
    initial_loss = history['train_loss'][0]
    final_loss = history['train_loss'][-1]
    
    assert final_loss < initial_loss


def test_predict(sample_returns):
    """Test prediction."""
    model = GARCHGRUModel(hidden_size=16, num_layers=1)
    
    # Train
    model.fit(sample_returns, epochs=5, verbose=False)
    
    # Predict
    predictions = model.predict(sample_returns, seq_length=20)
    
    assert len(predictions) > 0
    assert not np.isnan(predictions).any()
    # Predictions should be return forecasts (small values)
    assert np.abs(predictions).mean() < 1.0


def test_predict_before_fit_raises_error(sample_returns):
    """Test that prediction before fitting raises error."""
    model = GARCHGRUModel(hidden_size=16, num_layers=1)
    
    with pytest.raises(ValueError, match="Model must be fitted"):
        model.predict(sample_returns)


def test_save_and_load(sample_returns):
    """Test model save and load."""
    model1 = GARCHGRUModel(hidden_size=16, num_layers=1, learning_rate=0.01)
    
    # Train
    model1.fit(sample_returns[:150], epochs=5, verbose=False)
    
    # Save
    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "model.pt"
        model1.save(str(save_path))
        
        # Load into new model
        model2 = GARCHGRUModel()
        model2.load(str(save_path))
        
        # Check parameters match
        assert model2.hidden_size == 16
        assert model2.num_layers == 1
        assert model2.learning_rate == 0.01
        assert model2.model is not None
        
        # Check predictions match
        pred1 = model1.predict(sample_returns[150:], seq_length=20)
        pred2 = model2.predict(sample_returns[150:], seq_length=20)
        
        np.testing.assert_array_almost_equal(pred1, pred2, decimal=5)


def test_save_before_fit_raises_error():
    """Test that saving before fitting raises error."""
    model = GARCHGRUModel(hidden_size=16, num_layers=1)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "model.pt"
        
        with pytest.raises(ValueError, match="Model must be fitted"):
            model.save(str(save_path))


def test_different_seq_lengths(sample_returns):
    """Test with different sequence lengths."""
    for seq_len in [10, 20, 30]:
        model = GARCHGRUModel(hidden_size=16, num_layers=1)
        
        history = model.fit(
            sample_returns,
            epochs=3,
            seq_length=seq_len,
            verbose=False
        )
        
        predictions = model.predict(sample_returns, seq_length=seq_len)
        
        assert len(predictions) > 0


def test_device_cuda_if_available():
    """Test device selection."""
    model = GARCHGRUModel(hidden_size=16, num_layers=1, device=None)
    
    if torch.cuda.is_available():
        assert model.device.type == 'cuda'
    else:
        assert model.device.type == 'cpu'


def test_device_cpu_explicit():
    """Test explicit CPU device."""
    model = GARCHGRUModel(hidden_size=16, num_layers=1, device='cpu')
    
    assert model.device.type == 'cpu'


def test_model_reproducibility(sample_returns):
    """Test that results are reproducible with same seed."""
    torch.manual_seed(42)
    np.random.seed(42)
    
    model1 = GARCHGRUModel(hidden_size=16, num_layers=1)
    history1 = model1.fit(sample_returns, epochs=5, verbose=False)
    
    torch.manual_seed(42)
    np.random.seed(42)
    
    model2 = GARCHGRUModel(hidden_size=16, num_layers=1)
    history2 = model2.fit(sample_returns, epochs=5, verbose=False)
    
    # Training losses should be identical
    np.testing.assert_array_almost_equal(
        history1['train_loss'],
        history2['train_loss'],
        decimal=5
    )


def test_validation_split(sample_returns):
    """Test validation split."""
    model = GARCHGRUModel(hidden_size=16, num_layers=1)
    
    history = model.fit(
        sample_returns,
        epochs=5,
        validation_split=0.3,
        verbose=False
    )
    
    assert len(history['train_loss']) == 5
    assert len(history['val_loss']) == 5


def test_batch_size_variations(sample_returns):
    """Test different batch sizes."""
    for batch_size in [8, 16, 32]:
        model = GARCHGRUModel(hidden_size=16, num_layers=1)
        
        history = model.fit(
            sample_returns,
            epochs=3,
            batch_size=batch_size,
            verbose=False
        )
        
        assert len(history['train_loss']) == 3


def test_multilayer_gru(sample_returns):
    """Test with multiple GRU layers."""
    model = GARCHGRUModel(hidden_size=32, num_layers=3, dropout=0.2)
    
    history = model.fit(sample_returns, epochs=5, verbose=False)
    predictions = model.predict(sample_returns)
    
    assert len(predictions) > 0
    assert model.model.num_layers == 3


def test_predict_on_new_data(sample_returns):
    """Test prediction on different data than training."""
    model = GARCHGRUModel(hidden_size=16, num_layers=1)
    
    # Train on first half
    model.fit(sample_returns[:100], epochs=5, verbose=False)
    
    # Predict on second half
    predictions = model.predict(sample_returns[100:])
    
    assert len(predictions) > 0
    assert not np.isnan(predictions).any()
