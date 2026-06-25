#!/usr/bin/env python3
"""Universal training script that works with any model type from config.

This script:
1. Reads model type from config (or command line)
2. Loads appropriate hyperparameters from config
3. Trains the model
4. Saves to model registry

Works with all models: lightgbm, xgboost, enhanced_transformer, lstm_transformer, garch_gru
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import numpy as np
import pandas as pd

from core.config import load_config
from data.loaders.csv_loader import load_ohlcv_csv
from trainer.feature_engine import FeatureEngine
from trainer.models.model_factory import create_model_from_config, get_available_models
from trainer.models.model_registry import ModelRegistry

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description='Universal training script - works with all model types'
    )
    parser.add_argument('--symbol', type=str, default=None,
                        help='Symbol to train on (default: from config)')
    parser.add_argument('--model-type', type=str, default=None,
                        help='Model type (default: from config). Options: ' + 
                             ', '.join(get_available_models()))
    parser.add_argument('--timeframe', type=str, default=None,
                        help='Timeframe (default: from config): 1m, 5m, 15m, 30m, 1h, 1d')
    parser.add_argument('--epochs', type=int, default=None,
                        help='Training epochs (neural nets only, default: from config)')
    parser.add_argument('--batch-size', type=int, default=None,
                        help='Batch size (neural nets only, default: from config)')
    parser.add_argument('--data-dir', type=str, default='data',
                        help='Data directory')
    parser.add_argument('--registry', type=str, default='models/registry',
                        help='Model registry path')
    parser.add_argument('--no-save', action='store_true',
                        help='Do not save model to registry')
    
    args = parser.parse_args()
    
    # Load config
    try:
        cfg = load_config('config/dev.yaml')
        logger.info("Loaded configuration from config/dev.yaml")
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return 1
    
    # Get parameters (command line overrides config)
    symbol = args.symbol or cfg.get_primary_symbol()
    model_type = args.model_type or cfg.model.model_type
    timeframe = args.timeframe or cfg.data.timeframe
    epochs = args.epochs or cfg.model.epochs
    batch_size = args.batch_size or cfg.model.batch_size
    seq_length = cfg.model.seq_length
    
    # Check if model type is valid
    available = get_available_models()
    if model_type not in available:
        logger.error(f"Invalid model type: {model_type}")
        logger.error(f"Available: {', '.join(available)}")
        return 1
    
    logger.info("="*60)
    logger.info("UNIVERSAL MODEL TRAINING")
    logger.info("="*60)
    logger.info(f"Symbol: {symbol}")
    logger.info(f"Timeframe: {timeframe}")
    logger.info(f"Model type: {model_type}")
    if model_type in ['lightgbm', 'xgboost']:
        logger.info(f"Trees: {cfg.model.n_estimators}")
        logger.info(f"Learning rate: {cfg.model.tree_learning_rate}")
        logger.info(f"Max depth: {cfg.model.max_depth}")
    else:
        logger.info(f"Epochs: {epochs}")
        logger.info(f"Batch size: {batch_size}")
        logger.info(f"Sequence length: {seq_length}")
        if model_type == 'enhanced_transformer':
            logger.info(f"Model dim: {cfg.model.d_model}")
            logger.info(f"Attention heads: {cfg.model.nhead}")
        elif model_type in ['lstm_transformer', 'garch_gru']:
            logger.info(f"Hidden size: {cfg.model.hidden_size}")
    logger.info("="*60)
    
    # Load data
    logger.info(f"\nLoading data for {symbol}...")
    
    # Determine data file path
    data_dir = Path(args.data_dir)
    if timeframe == '1d':
        data_path = data_dir / 'raw' / f"{symbol}_daily.csv"
    else:
        data_path = data_dir / 'intraday' / f"{symbol}_{timeframe}.csv"
    
    if not data_path.exists():
        logger.error(f"Data file not found: {data_path}")
        logger.info(f"Try running: python scripts/download_intraday_data.py --symbol {symbol} --timeframe {timeframe}")
        return 1
    
    df = load_ohlcv_csv(str(data_path))
    logger.info(f"Loaded {len(df)} rows from {data_path}")
    
    # Compute features
    logger.info("Computing features...")
    feature_engine = FeatureEngine()
    features = feature_engine.compute_features(df)
    
    # Create target (future returns)
    target = df['close'].pct_change().shift(-1)
    
    # Drop NaN
    valid_idx = ~(features.isna().any(axis=1) | target.isna())
    features = features[valid_idx]
    target = target[valid_idx]
    
    logger.info(f"Features shape: {features.shape}")
    logger.info(f"Feature columns: {len(features.columns)}")
    
    # Train/test split (temporal)
    split_idx = int(len(features) * 0.7)
    features_train = features.iloc[:split_idx]
    features_test = features.iloc[split_idx:]
    target_train = target.iloc[:split_idx]
    target_test = target.iloc[split_idx:]
    
    logger.info(f"Training samples: {len(features_train)}")
    logger.info(f"Test samples: {len(features_test)}")
    
    # Create model from config
    logger.info(f"\nCreating {model_type} model from config...")
    model = create_model_from_config(cfg, model_type=model_type)
    
    # Train model
    logger.info(f"\nTraining {model_type.upper()}...")
    
    if model_type in ['lightgbm', 'xgboost']:
        # Tree-based models
        history = model.fit(
            features_train,
            target_train,
            validation_split=0.2,
            verbose=True,
        )
        
        # Predict
        predictions = model.predict(features_test)
        actual = target_test.values
        
        # Show feature importance
        logger.info("\nTop 15 most important features:")
        importance = model.get_feature_importance()
        print(importance.head(15).to_string(index=False))
        
    else:
        # Neural network models
        history = model.fit(
            features_train,
            target_train,
            epochs=epochs,
            batch_size=batch_size,
            seq_length=seq_length,
            validation_split=0.2,
            verbose=True,
        )
        
        # Predict
        predictions = model.predict(features_test, seq_length=seq_length)
        actual = target_test.values[-len(predictions):]
    
    # Calculate metrics
    accuracy = np.mean(np.sign(predictions) == np.sign(actual))
    mse = np.mean((predictions - actual) ** 2)
    mae = np.mean(np.abs(predictions - actual))
    
    logger.info("\n" + "="*60)
    logger.info("TRAINING RESULTS")
    logger.info("="*60)
    logger.info(f"Directional Accuracy: {accuracy:.2%}")
    logger.info(f"MSE: {mse:.8f}")
    logger.info(f"MAE: {mae:.8f}")
    logger.info("="*60)
    
    # Save model
    if not args.no_save:
        logger.info("\nSaving model to registry...")
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_dir = Path("models/temp")
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        # Determine file extension
        if model_type in ['lightgbm', 'lgb']:
            ext = '.txt'
        elif model_type in ['xgboost', 'xgb']:
            ext = '.json'
        else:
            ext = '.pt'
        
        # Save
        model_filename = f"{model_type}_{symbol}_{timeframe}_{timestamp}{ext}"
        model_path = temp_dir / model_filename
        model.save(str(model_path))
        
        # Register
        registry = ModelRegistry(base_path=args.registry)
        registry.register_model(
            model_name=model_type,
            model_path=model_path,
            metadata={
                'symbol': symbol,
                'timeframe': timeframe,
                'accuracy': float(accuracy),
                'mse': float(mse),
                'mae': float(mae),
                'trained_at': timestamp,
                'model_type': model_type,
            },
            tags=[symbol, timeframe, model_type],
        )
        
        logger.info(f"✅ Model saved: {model_path}")
        logger.info(f"✅ Registered in: {args.registry}")
    
    logger.info("\n🎉 Training completed successfully!")
    return 0


if __name__ == '__main__':
    sys.exit(main())
