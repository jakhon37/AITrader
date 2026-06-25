"""Tests for LSTM-Transformer model."""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import torch

from trainer.models.lstm_transformer import (
    LSTMTransformer,
    LSTMTransformerModel,
    PositionalEncoding,
)


@pytest.fixture
def sample_data():
    """Create sample feature data and targets."""
    np.random.seed(42)
    n = 200
    n_features = 5
    
    # Generate features
    features = np.random.randn(n, n_features) * 0.01
    dates = pd.date_range('2024-01-01', periods=n, freq='D')
    feature_df = pd.DataFrame(features, index=dates)
    
    # Generate targets (future returns)
    targets = np.random.randn(n) * 0.01
    target_series = pd.Series(targets, index=dates)
    
    return feature_df, target_series


def test_positional_encoding_init():
    """Test positional encoding initialization."""
    pos_enc = PositionalEncoding(d_model=128, max_len=1000)
    
    assert pos_enc.pe.shape == (1, 1000, 128)


def test_positional_encoding_forward():
    """Test positional encoding forward pass."""
    pos_enc = PositionalEncoding(d_model=64)
    
    x = torch.randn(4, 20, 64)  # (batch, seq_len, d_model)
    output = pos_enc(x)
    
    assert output.shape == (4, 20, 64)
    assert not torch.isnan(output).any()


def test_lstm_transformer_module_init():
    """Test LSTMTransformer module initialization."""
    model = LSTMTransformer(
        input_size=5,
        hidden_size=64,
        num_lstm_layers=2,
        num_transformer_layers=2,
        num_heads=4,
    )
    
    assert model.input_size == 5
    assert model.hidden_size == 64
    assert model.num_lstm_layers == 2
    assert model.num_transformer_layers == 2
    assert model.num_heads == 4


def test_lstm_transformer_forward_pass():
    """Test forward pass through model."""
    model = LSTMTransformer(input_size=5, hidden_size=64, num_heads=4)
    
    # Create dummy input: (batch=4, seq_len=20, features=5)
    x = torch.randn(4, 20, 5)
    
    output = model(x)
    
    assert output.shape == (4, 1)
    assert not torch.isnan(output).any()


def test_lstm_transformer_model_init():
    """Test LSTMTransformerModel wrapper initialization."""
    model = LSTMTransformerModel(input_size=5, hidden_size=64)
    
    assert model.input_size == 5
    assert model.hidden_size == 64
    assert model.model is None  # Not fitted yet


def test_prepare_sequences():
    """Test sequence preparation."""
    model = LSTMTransformerModel(hidden_size=64)
    
    features = np.random.randn(100, 5)
    targets = np.random.randn(100)
    
    X, y = model.prepare_sequences(features, targets, seq_length=10)
    
    assert X.shape == (90, 10, 5)  # 100 - 10 = 90 sequences
    assert y.shape == (90, 1)
    assert isinstance(X, torch.Tensor)
    assert isinstance(y, torch.Tensor)


def test_fit_basic(sample_data):
    """Test basic model fitting."""
    features, targets = sample_data
    model = LSTMTransformerModel(hidden_size=32, num_heads=2)
    
    history = model.fit(
        features,
        targets,
        epochs=5,
        batch_size=16,
        seq_length=10,
        verbose=False
    )
    
    assert 'train_loss' in history
    assert 'val_loss' in history
    assert len(history['train_loss']) == 5
    assert model.model is not None
    assert model.input_size == 5


def test_fit_reduces_loss(sample_data):
    """Test that training reduces loss."""
    features, targets = sample_data
    model = LSTMTransformerModel(hidden_size=64, num_heads=4)
    
    history = model.fit(
        features,
        targets,
        epochs=20,
        batch_size=16,
        verbose=False
    )
    
    # Loss should generally decrease
    initial_loss = history['train_loss'][0]
    final_loss = history['train_loss'][-1]
    
    assert final_loss < initial_loss


def test_predict(sample_data):
    """Test prediction."""
    features, targets = sample_data
    model = LSTMTransformerModel(hidden_size=32, num_heads=2)
    
    # Train
    model.fit(features, targets, epochs=5, verbose=False)
    
    # Predict
    predictions = model.predict(features, seq_length=20)
    
    assert len(predictions) > 0
    assert not np.isnan(predictions).any()
    # Predictions should be return forecasts (small values)
    assert np.abs(predictions).mean() < 1.0


def test_predict_before_fit_raises_error(sample_data):
    """Test that prediction before fitting raises error."""
    features, targets = sample_data
    model = LSTMTransformerModel(hidden_size=32)
    
    with pytest.raises(ValueError, match="Model must be fitted"):
        model.predict(features)


def test_save_and_load(sample_data):
    """Test model save and load."""
    features, targets = sample_data
    model1 = LSTMTransformerModel(
        hidden_size=32,
        num_heads=2,
        learning_rate=0.01
    )
    
    # Train
    model1.fit(features[:150], targets[:150], epochs=5, verbose=False)
    
    # Save
    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "model.pt"
        model1.save(str(save_path))
        
        # Load into new model
        model2 = LSTMTransformerModel()
        model2.load(str(save_path))
        
        # Check parameters match
        assert model2.input_size == 5
        assert model2.hidden_size == 32
        assert model2.num_heads == 2
        assert model2.learning_rate == 0.01
        assert model2.model is not None
        
        # Check predictions match
        pred1 = model1.predict(features[150:], seq_length=20)
        pred2 = model2.predict(features[150:], seq_length=20)
        
        np.testing.assert_array_almost_equal(pred1, pred2, decimal=5)


def test_save_before_fit_raises_error():
    """Test that saving before fitting raises error."""
    model = LSTMTransformerModel(hidden_size=32)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "model.pt"
        
        with pytest.raises(ValueError, match="Model must be fitted"):
            model.save(str(save_path))


def test_different_seq_lengths(sample_data):
    """Test with different sequence lengths."""
    features, targets = sample_data
    
    for seq_len in [10, 20, 30]:
        model = LSTMTransformerModel(hidden_size=32, num_heads=2)
        
        history = model.fit(
            features,
            targets,
            epochs=3,
            seq_length=seq_len,
            verbose=False
        )
        
        predictions = model.predict(features, seq_length=seq_len)
        
        assert len(predictions) > 0


def test_device_cuda_if_available():
    """Test device selection."""
    model = LSTMTransformerModel(hidden_size=32, device=None)
    
    if torch.cuda.is_available():
        assert model.device.type == 'cuda'
    else:
        assert model.device.type == 'cpu'


def test_device_cpu_explicit():
    """Test explicit CPU device."""
    model = LSTMTransformerModel(hidden_size=32, device='cpu')
    
    assert model.device.type == 'cpu'


def test_validation_split(sample_data):
    """Test validation split."""
    features, targets = sample_data
    model = LSTMTransformerModel(hidden_size=32, num_heads=2)
    
    history = model.fit(
        features,
        targets,
        epochs=5,
        validation_split=0.3,
        verbose=False
    )
    
    assert len(history['train_loss']) == 5
    assert len(history['val_loss']) == 5


def test_batch_size_variations(sample_data):
    """Test different batch sizes."""
    features, targets = sample_data
    
    for batch_size in [8, 16, 32]:
        model = LSTMTransformerModel(hidden_size=32, num_heads=2)
        
        history = model.fit(
            features,
            targets,
            epochs=3,
            batch_size=batch_size,
            verbose=False
        )
        
        assert len(history['train_loss']) == 3


def test_different_architectures(sample_data):
    """Test with different architectural configurations."""
    features, targets = sample_data
    
    configs = [
        {'num_lstm_layers': 1, 'num_transformer_layers': 1, 'num_heads': 2},
        {'num_lstm_layers': 2, 'num_transformer_layers': 2, 'num_heads': 4},
        {'num_lstm_layers': 3, 'num_transformer_layers': 1, 'num_heads': 2},
    ]
    
    for config in configs:
        model = LSTMTransformerModel(hidden_size=32, **config)
        
        history = model.fit(
            features,
            targets,
            epochs=3,
            verbose=False
        )
        
        predictions = model.predict(features)
        
        assert len(predictions) > 0


def test_predict_on_new_data(sample_data):
    """Test prediction on different data than training."""
    features, targets = sample_data
    model = LSTMTransformerModel(hidden_size=32, num_heads=2)
    
    # Train on first half
    model.fit(features[:100], targets[:100], epochs=5, verbose=False)
    
    # Predict on second half
    predictions = model.predict(features[100:])
    
    assert len(predictions) > 0
    assert not np.isnan(predictions).any()


def test_gradient_clipping_prevents_explosion(sample_data):
    """Test that gradient clipping prevents explosions."""
    features, targets = sample_data
    model = LSTMTransformerModel(hidden_size=64, num_heads=4, learning_rate=0.1)
    
    # High learning rate could cause explosions without clipping
    history = model.fit(
        features,
        targets,
        epochs=10,
        verbose=False
    )
    
    # Losses should not be NaN or inf
    assert not any(np.isnan(history['train_loss']))
    assert not any(np.isinf(history['train_loss']))


def test_input_size_auto_inference(sample_data):
    """Test automatic input size inference."""
    features, targets = sample_data
    model = LSTMTransformerModel(input_size=None, hidden_size=32, num_heads=2)
    
    assert model.input_size is None
    
    model.fit(features, targets, epochs=3, verbose=False)
    
    # Should be inferred from data
    assert model.input_size == 5
