"""Integration test for full model pipeline.

Tests the complete flow from data loading through feature computation,
model training, ensemble creation, meta-labeling, and model registry.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from data.loaders.csv_loader import load_ohlcv_csv
from features.feature_engine import FeatureEngine
from models.ensemble import EnsembleModel
from models.garch_gru import GARCHGRUModel
from models.lstm_transformer import LSTMTransformerModel
from models.meta_labeler import MetaLabeler
from models.model_registry import ModelRegistry


@pytest.fixture
def sample_market_data():
    """Create sample OHLCV data."""
    np.random.seed(42)
    n = 150
    
    dates = pd.date_range('2024-01-01', periods=n, freq='D')
    
    # Generate realistic price data
    close = 100 * np.exp(np.cumsum(np.random.randn(n) * 0.01))
    high = close * (1 + np.abs(np.random.rand(n) * 0.01))
    low = close * (1 - np.abs(np.random.rand(n) * 0.01))
    open_ = close * (1 + (np.random.rand(n) - 0.5) * 0.005)
    volume = np.random.randint(1000, 10000, n)
    
    return pd.DataFrame({
        'open': open_,
        'high': high,
        'low': low,
        'close': close,
        'volume': volume,
    }, index=dates)


def test_full_pipeline_integration(sample_market_data):
    """Test complete pipeline from data to predictions."""
    
    # 1. Feature Engineering
    feature_engine = FeatureEngine()
    features = feature_engine.compute_features(sample_market_data)
    
    assert len(features) > 0
    assert not features.empty
    
    # 2. Prepare data
    target = sample_market_data['close'].pct_change().shift(-1)
    valid_idx = features.dropna().index.intersection(target.dropna().index)
    features = features.loc[valid_idx]
    target = target.loc[valid_idx]
    
    # Train/test split
    split_idx = int(len(features) * 0.7)
    features_train = features.iloc[:split_idx]
    features_test = features.iloc[split_idx:]
    target_train = target.iloc[:split_idx]
    target_test = target.iloc[split_idx:]
    
    assert len(features_train) > 20  # Need enough for sequence
    assert len(features_test) > 10
    
    # 3. Train GARCH-GRU
    garch_model = GARCHGRUModel(hidden_size=16, num_layers=1, device='cpu')
    garch_model.fit(target_train, epochs=3, batch_size=8, verbose=False)
    
    garch_predictions = garch_model.predict(target_test, seq_length=20)
    
    assert len(garch_predictions) > 0
    assert not np.isnan(garch_predictions).any()
    
    # 4. Train LSTM-Transformer
    lstm_model = LSTMTransformerModel(
        hidden_size=32,
        num_lstm_layers=1,
        num_transformer_layers=1,
        num_heads=2,
        device='cpu'
    )
    lstm_model.fit(features_train, target_train, epochs=3, batch_size=8, verbose=False)
    
    lstm_predictions = lstm_model.predict(features_test, seq_length=20)
    
    assert len(lstm_predictions) > 0
    assert not np.isnan(lstm_predictions).any()
    
    # 5. Create Ensemble
    ensemble = EnsembleModel(
        models=[garch_model, lstm_model],
        strategy='weighted_average',
    )
    
    ensemble_predictions = ensemble.predict(features_test, seq_length=20)
    
    assert len(ensemble_predictions) > 0
    assert not np.isnan(ensemble_predictions).any()
    
    # 6. Train Meta-Labeler
    # Align predictions and features
    min_len_train = min(
        len(garch_model.predict(target_train, seq_length=20)),
        len(lstm_model.predict(features_train, seq_length=20))
    )
    
    ensemble_pred_train = ensemble.predict(features_train, seq_length=20)[:min_len_train]
    actual_train = target_train.values[-min_len_train:]
    features_for_meta_train = features_train.iloc[-min_len_train:]
    
    min_len_test = min(len(garch_predictions), len(lstm_predictions))
    ensemble_pred_test = ensemble_predictions[:min_len_test]
    actual_test = target_test.values[-min_len_test:]
    features_for_meta_test = features_test.iloc[-min_len_test:]
    
    meta_labeler = MetaLabeler(confidence_threshold=0.55, n_estimators=50, max_depth=3)
    meta_labeler.fit(
        features_for_meta_train,
        ensemble_pred_train,
        actual_train,
    )
    
    signals, sizes = meta_labeler.get_signal_with_size(
        features_for_meta_test,
        ensemble_pred_test,
        strategy='linear',
    )
    
    assert len(signals) == len(sizes)
    assert (sizes >= 0).all() and (sizes <= 1).all()
    
    # 7. Save to Registry
    with tempfile.TemporaryDirectory() as tmpdir:
        registry = ModelRegistry(base_path=tmpdir)
        
        # Save models
        garch_path = Path(tmpdir) / "garch_temp.pt"
        garch_model.save(str(garch_path))
        
        v1 = registry.register_model(
            'garch_gru',
            garch_path,
            metadata={'accuracy': 0.55},
            tags=['test'],
        )
        
        lstm_path = Path(tmpdir) / "lstm_temp.pt"
        lstm_model.save(str(lstm_path))
        
        v2 = registry.register_model(
            'lstm_transformer',
            lstm_path,
            metadata={'accuracy': 0.58},
            tags=['test'],
        )
        
        # Verify registry
        assert 'garch_gru' in registry.list_models()
        assert 'lstm_transformer' in registry.list_models()
        
        # Load and predict
        loaded_path = registry.get_model_path('garch_gru', v1)
        assert loaded_path.exists()
    
    # 8. Performance metrics
    actual_aligned = actual_test[:len(ensemble_pred_test)]
    
    # Directional accuracy
    direction_correct = np.sign(ensemble_pred_test) == np.sign(actual_aligned)
    accuracy = np.mean(direction_correct)
    
    # With meta-labeling
    sized_returns = signals * sizes * actual_aligned
    n_trades = np.sum(sizes > 0)
    trade_frequency = n_trades / len(sizes)
    
    assert 0 <= accuracy <= 1
    assert 0 <= trade_frequency <= 1
    assert n_trades < len(signals)  # Should filter some trades


def test_model_comparison_workflow(sample_market_data):
    """Test comparing multiple model versions."""
    
    feature_engine = FeatureEngine()
    features = feature_engine.compute_features(sample_market_data)
    target = sample_market_data['close'].pct_change().shift(-1)
    
    valid_idx = features.dropna().index.intersection(target.dropna().index)
    features = features.loc[valid_idx]
    target = target.loc[valid_idx]
    
    # Train two models with different configs
    model1 = GARCHGRUModel(hidden_size=16, num_layers=1, device='cpu')
    model1.fit(target, epochs=2, verbose=False)
    
    model2 = GARCHGRUModel(hidden_size=32, num_layers=2, device='cpu')
    model2.fit(target, epochs=2, verbose=False)
    
    # Save to registry
    with tempfile.TemporaryDirectory() as tmpdir:
        registry = ModelRegistry(base_path=tmpdir)
        
        path1 = Path(tmpdir) / "model1.pt"
        model1.save(str(path1))
        v1 = registry.register_model(
            'garch_gru',
            path1,
            version='v1',
            metadata={'metrics': {'accuracy': 0.52}},
        )
        
        path2 = Path(tmpdir) / "model2.pt"
        model2.save(str(path2))
        v2 = registry.register_model(
            'garch_gru',
            path2,
            version='v2',
            metadata={'metrics': {'accuracy': 0.58}},
        )
        
        # Compare
        comparison = registry.compare_models(
            [('garch_gru', 'v1'), ('garch_gru', 'v2')],
            metric='accuracy',
        )
        
        assert len(comparison) == 2
        assert 'accuracy' in comparison.columns
        
        # Get best
        best = registry.get_best_model(model_type='garch_gru', metric='accuracy')
        assert best is not None
        assert best[1] == 'v2'  # v2 should be best


def test_ensemble_diversity(sample_market_data):
    """Test ensemble diversity scoring."""
    
    feature_engine = FeatureEngine()
    features = feature_engine.compute_features(sample_market_data)
    target = sample_market_data['close'].pct_change().shift(-1)
    
    valid_idx = features.dropna().index.intersection(target.dropna().index)
    features = features.loc[valid_idx]
    target = target.loc[valid_idx]
    
    # Train models with different seeds
    np.random.seed(42)
    model1 = GARCHGRUModel(hidden_size=16, num_layers=1, device='cpu')
    model1.fit(target, epochs=2, verbose=False)
    
    np.random.seed(123)
    model2 = GARCHGRUModel(hidden_size=16, num_layers=1, device='cpu')
    model2.fit(target, epochs=2, verbose=False)
    
    # Create ensemble
    ensemble = EnsembleModel(models=[model1, model2])
    
    # Calculate diversity
    diversity = ensemble.get_diversity_score(features, seq_length=20)
    
    # Should have some diversity (models trained with different seeds)
    assert diversity >= 0
    assert diversity <= 2


def test_meta_labeler_filters_bad_predictions(sample_market_data):
    """Test that meta-labeler filters low-confidence predictions."""
    
    feature_engine = FeatureEngine()
    features = feature_engine.compute_features(sample_market_data)
    target = sample_market_data['close'].pct_change().shift(-1)
    
    valid_idx = features.dropna().index.intersection(target.dropna().index)
    features = features.loc[valid_idx]
    target = target.loc[valid_idx]
    
    # Create intentionally bad predictions
    bad_predictions = -target.values  # Opposite direction
    
    # Train meta-labeler
    split_idx = int(len(features) * 0.7)
    
    meta_labeler = MetaLabeler(confidence_threshold=0.6, n_estimators=50)
    meta_labeler.fit(
        features.iloc[:split_idx],
        bad_predictions[:split_idx],
        target.values[:split_idx],
    )
    
    # Evaluate
    signals, sizes = meta_labeler.get_signal_with_size(
        features.iloc[split_idx:],
        bad_predictions[split_idx:],
        strategy='linear',
    )
    
    # Should filter out many bad predictions
    trade_frequency = np.sum(sizes > 0) / len(sizes)
    
    # With bad predictions, should be conservative
    assert trade_frequency < 0.8  # Should reject at least some


def test_model_promotion_workflow():
    """Test model promotion from dev to staging to prod."""
    
    with tempfile.TemporaryDirectory() as tmpdir:
        registry = ModelRegistry(base_path=tmpdir)
        
        # Create dummy model file
        model_file = Path(tmpdir) / "test_model.pt"
        model_file.write_text("dummy model")
        
        # Register model
        version = registry.register_model(
            'test_model',
            model_file,
            metadata={'metrics': {'sharpe': 1.5}},
        )
        
        # Check initial status
        metadata = registry.get_metadata('test_model', version)
        assert metadata['status'] == 'dev'
        
        # Promote to staging
        registry.promote_model('test_model', version, 'staging')
        metadata = registry.get_metadata('test_model', version)
        assert metadata['status'] == 'staging'
        
        # Promote to prod
        registry.promote_model('test_model', version, 'prod')
        metadata = registry.get_metadata('test_model', version)
        assert metadata['status'] == 'prod'
        
        # Get production model
        result = registry.get_production_model('test_model')
        assert result is not None
        assert result[0] == version


def test_end_to_end_prediction_flow(sample_market_data):
    """Test complete prediction flow as would be used in production."""
    
    # Setup
    feature_engine = FeatureEngine()
    features = feature_engine.compute_features(sample_market_data)
    target = sample_market_data['close'].pct_change().shift(-1)
    
    valid_idx = features.dropna().index.intersection(target.dropna().index)
    features = features.loc[valid_idx]
    target = target.loc[valid_idx]
    
    split_idx = int(len(features) * 0.7)
    
    # Train models
    model1 = GARCHGRUModel(hidden_size=16, num_layers=1, device='cpu')
    model1.fit(target.iloc[:split_idx], epochs=2, verbose=False)
    
    model2 = LSTMTransformerModel(hidden_size=32, num_heads=2, device='cpu')
    model2.fit(features.iloc[:split_idx], target.iloc[:split_idx], epochs=2, verbose=False)
    
    # Create ensemble
    ensemble = EnsembleModel(models=[model1, model2], strategy='simple_average')
    
    # Get predictions
    test_features = features.iloc[split_idx:]
    
    # Step 1: Ensemble prediction
    base_predictions = ensemble.predict(test_features, seq_length=20)
    
    # Step 2: Get confidence
    predictions, confidence = ensemble.get_predictions_with_confidence(test_features, seq_length=20)
    
    assert len(predictions) == len(confidence)
    
    # Step 3: Meta-labeling (would need trained meta-labeler in prod)
    # For this test, just verify the flow works
    
    # Final: Apply position sizing
    # In production, would combine signal direction with meta-labeler size
    signals = np.sign(predictions)
    position_sizes = confidence  # Use confidence as size for this test
    
    final_positions = signals * position_sizes
    
    assert len(final_positions) > 0
    assert (np.abs(final_positions) <= 1).all()
