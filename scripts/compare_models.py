#!/usr/bin/env python3
"""Compare different model architectures on the same dataset.

This script trains multiple models and compares their performance
to find the best architecture for your trading strategy.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from core.config import load_config
from data.loaders.csv_loader import load_ohlcv_csv
from trainer.feature_engine import FeatureEngine
from trainer.models.model_factory import (
    create_model,
    get_available_models,
    get_recommended_hyperparameters,
    print_model_comparison,
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def calculate_metrics(predictions: np.ndarray, actual: np.ndarray) -> dict:
    """Calculate comprehensive performance metrics.
    
    Args:
        predictions: Predicted values
        actual: Actual values
        
    Returns:
        Dictionary of metrics
    """
    # Direction accuracy (most important for trading)
    directional_accuracy = np.mean(np.sign(predictions) == np.sign(actual))
    
    # MSE and RMSE
    mse = np.mean((predictions - actual) ** 2)
    rmse = np.sqrt(mse)
    
    # MAE
    mae = np.mean(np.abs(predictions - actual))
    
    # R-squared
    ss_res = np.sum((actual - predictions) ** 2)
    ss_tot = np.sum((actual - actual.mean()) ** 2)
    r2 = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0
    
    # Profit simulation (simple)
    # Buy when prediction > 0, Sell when prediction < 0
    signals = np.sign(predictions)
    returns = actual * signals
    cumulative_return = np.sum(returns)
    sharpe_ratio = returns.mean() / (returns.std() + 1e-8) * np.sqrt(252)  # Annualized
    
    return {
        'directional_accuracy': float(directional_accuracy),
        'mse': float(mse),
        'rmse': float(rmse),
        'mae': float(mae),
        'r2': float(r2),
        'cumulative_return': float(cumulative_return),
        'sharpe_ratio': float(sharpe_ratio),
    }


def train_and_evaluate_model(
    model_type: str,
    features_train: pd.DataFrame,
    target_train: pd.Series,
    features_test: pd.DataFrame,
    target_test: pd.Series,
    device: str = 'cpu',
    epochs: int = 50,
    batch_size: int = 256,
    seq_length: int = 20,
) -> dict:
    """Train and evaluate a single model.
    
    Args:
        model_type: Type of model to train
        features_train: Training features
        target_train: Training target
        features_test: Test features
        target_test: Test target
        device: Device to use
        epochs: Training epochs (for neural nets)
        batch_size: Batch size
        seq_length: Sequence length (for sequential models)
        
    Returns:
        Dictionary with results
    """
    logger.info(f"{'='*60}")
    logger.info(f"Training {model_type.upper()}")
    logger.info(f"{'='*60}")
    
    start_time = time.time()
    
    try:
        # Get recommended hyperparameters
        gpu_available = device in ['cuda', 'gpu']
        hyperparams = get_recommended_hyperparameters(model_type, use_case='general', gpu_available=gpu_available)
        
        # Create model
        model = create_model(model_type, device=device, **hyperparams)
        
        # Train model
        if model_type in ['lightgbm', 'xgboost']:
            # Tree-based models don't need sequences
            history = model.fit(
                features_train,
                target_train,
                validation_split=0.2,
                verbose=True,
            )
            
            # Predict on test set
            predictions = model.predict(features_test)
            actual = target_test.values
            
        else:
            # Neural network models need sequences
            history = model.fit(
                features_train,
                target_train,
                epochs=epochs,
                batch_size=batch_size,
                seq_length=seq_length,
                validation_split=0.2,
                verbose=True,
            )
            
            # Predict on test set
            predictions = model.predict(features_test, seq_length=seq_length)
            actual = target_test.values[-len(predictions):]
        
        training_time = time.time() - start_time
        
        # Calculate metrics
        metrics = calculate_metrics(predictions, actual)
        metrics['training_time_seconds'] = training_time
        metrics['training_time_minutes'] = training_time / 60
        
        logger.info(f"\n{model_type.upper()} Results:")
        logger.info(f"  Training time: {training_time:.1f}s ({training_time/60:.1f}min)")
        logger.info(f"  Directional accuracy: {metrics['directional_accuracy']:.2%}")
        logger.info(f"  RMSE: {metrics['rmse']:.6f}")
        logger.info(f"  MAE: {metrics['mae']:.6f}")
        logger.info(f"  R²: {metrics['r2']:.4f}")
        logger.info(f"  Cumulative return: {metrics['cumulative_return']:.6f}")
        logger.info(f"  Sharpe ratio: {metrics['sharpe_ratio']:.4f}")
        
        return {
            'model_type': model_type,
            'success': True,
            'metrics': metrics,
            'history': history,
        }
        
    except Exception as e:
        logger.error(f"Error training {model_type}: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            'model_type': model_type,
            'success': False,
            'error': str(e),
        }


def main():
    parser = argparse.ArgumentParser(description='Compare different model architectures')
    parser.add_argument('--symbol', type=str, default=None,
                        help='Symbol to train on (default: from config)')
    parser.add_argument('--models', type=str, nargs='+', default=['all'],
                        help='Models to compare (default: all available)')
    parser.add_argument('--epochs', type=int, default=30,
                        help='Training epochs for neural nets (default: 30)')
    parser.add_argument('--batch-size', type=int, default=256,
                        help='Batch size (default: 256)')
    parser.add_argument('--seq-length', type=int, default=20,
                        help='Sequence length (default: 20)')
    parser.add_argument('--data-dir', type=str, default='data/raw',
                        help='Data directory')
    parser.add_argument('--list-models', action='store_true',
                        help='List available models and exit')
    
    args = parser.parse_args()
    
    # List models if requested
    if args.list_models:
        print_model_comparison()
        return
    
    # Load config
    try:
        cfg = load_config('config/dev.yaml')
        symbol = args.symbol or cfg.get_primary_symbol()
        device = 'cuda' if cfg.model.model_type != 'cpu' else 'cpu'
    except Exception as e:
        logger.warning(f"Could not load config: {e}. Using defaults.")
        symbol = args.symbol or 'eurusd'
        device = 'cpu'
    
    # Detect GPU
    try:
        import torch
        if torch.cuda.is_available():
            device = 'cuda'
            logger.info(f"GPU detected: {torch.cuda.get_device_name(0)}")
        else:
            device = 'cpu'
            logger.info("Using CPU")
    except ImportError:
        device = 'cpu'
    
    # Get available models
    available_models = get_available_models()
    
    # Determine which models to test
    if 'all' in args.models:
        models_to_test = [m for m in available_models if m not in ['lgb', 'xgb']]  # Exclude aliases
    else:
        models_to_test = [m for m in args.models if m in available_models]
    
    if not models_to_test:
        logger.error(f"No valid models specified. Available: {', '.join(available_models)}")
        return
    
    logger.info(f"\n{'='*60}")
    logger.info(f"MODEL COMPARISON")
    logger.info(f"{'='*60}")
    logger.info(f"Symbol: {symbol}")
    logger.info(f"Models to test: {', '.join(models_to_test)}")
    logger.info(f"Device: {device}")
    logger.info(f"Epochs (neural nets): {args.epochs}")
    logger.info(f"Batch size: {args.batch_size}")
    logger.info(f"Sequence length: {args.seq_length}")
    logger.info(f"{'='*60}\n")
    
    # Load data
    logger.info("Loading data...")
    data_dir = Path(args.data_dir)
    symbol_normalized = symbol.lower().replace('_', '').replace('/', '')
    csv_path = data_dir / f"{symbol_normalized}_daily.csv"
    
    if not csv_path.exists():
        logger.error(f"Data file not found: {csv_path}")
        return
    
    df = load_ohlcv_csv(str(csv_path))
    logger.info(f"Loaded {len(df)} rows")
    
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
    logger.info(f"Target shape: {target.shape}")
    
    # Train/test split (temporal)
    split_idx = int(len(features) * 0.7)
    features_train = features.iloc[:split_idx]
    features_test = features.iloc[split_idx:]
    target_train = target.iloc[:split_idx]
    target_test = target.iloc[split_idx:]
    
    logger.info(f"Train size: {len(features_train)}, Test size: {len(features_test)}\n")
    
    # Train all models
    results = []
    for model_type in models_to_test:
        result = train_and_evaluate_model(
            model_type=model_type,
            features_train=features_train,
            target_train=target_train,
            features_test=features_test,
            target_test=target_test,
            device=device,
            epochs=args.epochs,
            batch_size=args.batch_size,
            seq_length=args.seq_length,
        )
        results.append(result)
        logger.info("")  # Blank line
    
    # Print comparison table
    logger.info(f"\n{'='*100}")
    logger.info("FINAL COMPARISON")
    logger.info(f"{'='*100}")
    
    successful_results = [r for r in results if r['success']]
    
    if not successful_results:
        logger.error("No models trained successfully!")
        return
    
    # Create comparison DataFrame
    comparison_data = []
    for r in successful_results:
        m = r['metrics']
        comparison_data.append({
            'Model': r['model_type'],
            'Accuracy (%)': f"{m['directional_accuracy']*100:.2f}",
            'RMSE': f"{m['rmse']:.6f}",
            'MAE': f"{m['mae']:.6f}",
            'R²': f"{m['r2']:.4f}",
            'Sharpe': f"{m['sharpe_ratio']:.4f}",
            'Time (min)': f"{m['training_time_minutes']:.1f}",
        })
    
    df_comparison = pd.DataFrame(comparison_data)
    print("\n" + df_comparison.to_string(index=False))
    
    # Find best models
    best_accuracy = max(successful_results, key=lambda r: r['metrics']['directional_accuracy'])
    best_sharpe = max(successful_results, key=lambda r: r['metrics']['sharpe_ratio'])
    fastest = min(successful_results, key=lambda r: r['metrics']['training_time_seconds'])
    
    logger.info(f"\n{'='*100}")
    logger.info("WINNERS:")
    logger.info(f"  🎯 Best Accuracy: {best_accuracy['model_type']} "
                f"({best_accuracy['metrics']['directional_accuracy']:.2%})")
    logger.info(f"  💰 Best Sharpe: {best_sharpe['model_type']} "
                f"({best_sharpe['metrics']['sharpe_ratio']:.4f})")
    logger.info(f"  ⚡ Fastest: {fastest['model_type']} "
                f"({fastest['metrics']['training_time_minutes']:.1f}min)")
    logger.info(f"{'='*100}\n")
    
    # Save results
    results_dir = Path('reports/model_comparison')
    results_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_file = results_dir / f"comparison_{symbol}_{timestamp}.csv"
    df_comparison.to_csv(results_file, index=False)
    logger.info(f"Results saved to: {results_file}")


if __name__ == '__main__':
    main()
