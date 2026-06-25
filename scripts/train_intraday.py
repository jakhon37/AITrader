#!/usr/bin/env python3
"""Train models on intraday data (1m, 5m, 15m, etc.).

This script trains GARCH-GRU and LSTM-Transformer models on intraday
timeframe data. Due to Yahoo Finance limitations:
- 1m data: 7 days max
- Other intraday: 60 days max

Examples:
    # Train on 1-minute BTCUSD data
    python scripts/train_intraday.py --symbol btcusd --timeframe 1m --epochs 50
    
    # Train on 5-minute data with custom split
    python scripts/train_intraday.py --symbol eurusd --timeframe 5m --split 0.8
    
    # Train in Docker with GPU
    ./docker/docker_dev_train.sh --script scripts/train_intraday.py --symbol btcusd --timeframe 1m
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

from data.loaders.csv_loader import load_ohlcv_csv
from trainer.feature_engine import FeatureEngine
from trainer.models.ensemble import EnsembleModel
from trainer.models.garch_gru import GARCHGRUModel
from trainer.models.lstm_transformer import LSTMTransformerModel
from trainer.models.meta_labeler import MetaLabeler
from trainer.models.model_registry import ModelRegistry

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class IntradayTrainer:
    """Train models on intraday data."""

    def __init__(
        self,
        symbol: str = "btcusd",
        timeframe: str = "1m",
        data_dir: str = "data/raw",
        registry_path: str = "models/registry",
        random_seed: int = 42,
    ) -> None:
        """Initialize trainer."""
        self.symbol = symbol.lower()
        self.timeframe = timeframe
        self.data_dir = Path(data_dir)
        self.registry_path = registry_path
        self.random_seed = random_seed
        
        # Set random seeds
        np.random.seed(random_seed)
        
        # Detect GPU availability
        import torch
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            logger.info(f"🎮 GPU detected: {gpu_name}")
            logger.info(f"   CUDA version: {torch.version.cuda}")
            logger.info(f"   PyTorch CUDA available: {torch.cuda.is_available()}")
        else:
            logger.info("💻 Using CPU (no GPU detected)")
        
        # Initialize components
        self.feature_engine = FeatureEngine()
        self.registry = ModelRegistry(base_path=registry_path)
        
        logger.info(f"🚀 Initialized trainer for {symbol} at {timeframe} timeframe")

    def load_and_prepare_data(self, train_split: float = 0.7):
        """Load and prepare intraday training data."""
        logger.info(f"📊 Loading {self.timeframe} data for {self.symbol}")
        
        # Load intraday data from CSV
        csv_path = self.data_dir / f"{self.symbol}_{self.timeframe}.csv"
        if not csv_path.exists():
            raise FileNotFoundError(
                f"❌ Data file not found: {csv_path}\n"
                f"💡 Download it first with:\n"
                f"   python scripts/download_intraday_data.py --timeframe {self.timeframe} --symbols {self.symbol}"
            )
        
        data = load_ohlcv_csv(csv_path)
        logger.info(f"   Loaded {len(data)} bars from {data.index[0]} to {data.index[-1]}")
        
        # Compute features
        logger.info("🔧 Computing features...")
        features = self.feature_engine.compute_features(data)
        
        # Create target (future returns for next bar)
        target = data['close'].pct_change().shift(-1)
        
        # Align features and target
        valid_idx = features.dropna().index.intersection(target.dropna().index)
        features = features.loc[valid_idx]
        target = target.loc[valid_idx]
        
        logger.info(f"   Features shape: {features.shape}, Target shape: {target.shape}")
        
        # Train/test split (temporal)
        split_idx = int(len(features) * train_split)
        
        features_train = features.iloc[:split_idx]
        features_test = features.iloc[split_idx:]
        target_train = target.iloc[:split_idx]
        target_test = target.iloc[split_idx:]
        
        logger.info(f"   Train: {len(features_train)} bars, Test: {len(features_test)} bars")
        logger.info(f"   Train period: {features_train.index[0]} to {features_train.index[-1]}")
        logger.info(f"   Test period: {features_test.index[0]} to {features_test.index[-1]}")
        
        return features_train, features_test, target_train, target_test, data

    def train_garch_gru(
        self,
        features_train,
        target_train,
        features_test,
        target_test,
        epochs: int = 50,
        batch_size: int = 256,  # GPU-optimized default
    ):
        """Train GARCH-GRU model."""
        logger.info("\n" + "="*60)
        logger.info("🔮 Training GARCH-GRU Model")
        logger.info("="*60)
        logger.info(f"   Batch size: {batch_size}")
        
        model = GARCHGRUModel(
            hidden_size=64,
            num_layers=2,
            dropout=0.2,
            device=str(self.device),  # Auto-detect GPU
        )
        
        # Extract returns for GARCH (first feature column)
        returns_train = features_train.iloc[:, 0]  # First column is typically return_1
        
        history = model.fit(
            returns=returns_train,
            epochs=epochs,
            batch_size=batch_size,
            seq_length=20,
            verbose=True,
        )
        
        # Predict
        predictions = model.predict(returns=features_test.iloc[:, 0], seq_length=20)
        
        # Calculate metrics - align predictions with actual values
        # Predictions start from index 20 (seq_length) onwards
        # Take minimum length to ensure alignment
        min_len = min(len(predictions), len(target_test) - 20)
        predictions = predictions[:min_len]
        actual = target_test.iloc[20:20+min_len].values
        
        mse = np.mean((predictions - actual) ** 2)
        mae = np.mean(np.abs(predictions - actual))
        
        logger.info(f"\n✅ GARCH-GRU Training Complete")
        logger.info(f"   MSE: {mse:.6f}")
        logger.info(f"   MAE: {mae:.6f}")
        
        return model, {"mse": mse, "mae": mae, "history": history}

    def train_lstm_transformer(
        self,
        features_train,
        target_train,
        features_test,
        target_test,
        epochs: int = 50,
        batch_size: int = 256,  # GPU-optimized default
    ):
        """Train LSTM-Transformer model."""
        logger.info("\n" + "="*60)
        logger.info("🧠 Training LSTM-Transformer Model")
        logger.info("="*60)
        logger.info(f"   Batch size: {batch_size}")
        
        model = LSTMTransformerModel(
            input_size=features_train.shape[1],
            hidden_size=128,
            num_lstm_layers=2,
            num_transformer_layers=2,
            num_heads=4,
            dropout=0.2,
            device=str(self.device),  # Auto-detect GPU
        )
        
        history = model.fit(
            features=features_train,
            target=target_train,
            epochs=epochs,
            batch_size=batch_size,
            seq_length=20,
            verbose=True,
        )
        
        # Predict
        predictions = model.predict(features=features_test, seq_length=20)
        
        # Calculate metrics - align predictions with actual values
        # Predictions start from index 20 (seq_length) onwards
        # Take minimum length to ensure alignment
        min_len = min(len(predictions), len(target_test) - 20)
        predictions = predictions[:min_len]
        actual = target_test.iloc[20:20+min_len].values
        
        mse = np.mean((predictions - actual) ** 2)
        mae = np.mean(np.abs(predictions - actual))
        
        logger.info(f"\n✅ LSTM-Transformer Training Complete")
        logger.info(f"   MSE: {mse:.6f}")
        logger.info(f"   MAE: {mae:.6f}")
        
        return model, {"mse": mse, "mae": mae, "history": history}

    def save_models(self, models: dict, metrics: dict):
        """Save trained models to temp directory."""
        logger.info("\n" + "="*60)
        logger.info("💾 Saving Models")
        logger.info("="*60)
        
        temp_dir = Path("models/temp")
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        for model_name, model in models.items():
            model_path = temp_dir / f"{model_name}_{self.symbol}_{self.timeframe}_{timestamp}.pt"
            model.save(str(model_path))
            logger.info(f"   ✅ Saved {model_name} to {model_path}")
        
        logger.info(f"\n🎉 All models saved successfully!")
        logger.info(f"   Location: {temp_dir}")
        logger.info(f"   Timeframe: {self.timeframe}")
        logger.info(f"   Symbol: {self.symbol}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Train models on intraday data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use config defaults
  python scripts/train_intraday.py
  
  # Override specific settings
  python scripts/train_intraday.py --symbol btcusd --epochs 100
  
  # Use different config file
  python scripts/train_intraday.py --config config/prod.yaml
        """
    )
    
    # Load config for defaults
    from core.config import load_config
    try:
        cfg = load_config()
        default_symbol = cfg.get_primary_symbol()
        default_timeframe = cfg.data.timeframe
        default_epochs = cfg.model.epochs
        default_batch_size = cfg.model.batch_size
    except Exception:
        # Fallback if config fails
        default_symbol = "btcusd"
        default_timeframe = "1m"
        default_epochs = 50
        default_batch_size = 256
    
    parser.add_argument(
        "--symbol",
        "-s",
        default=default_symbol,
        help=f"Symbol to train on (default: from config or {default_symbol})"
    )
    parser.add_argument(
        "--timeframe",
        "-t",
        default=default_timeframe,
        choices=["1m", "2m", "5m", "15m", "30m", "1h"],
        help=f"Timeframe for training (default: from config or {default_timeframe})"
    )
    parser.add_argument(
        "--epochs",
        "-e",
        type=int,
        default=default_epochs,
        help=f"Number of training epochs (default: from config or {default_epochs})"
    )
    parser.add_argument(
        "--batch-size",
        "-b",
        type=int,
        default=default_batch_size,
        help=f"Batch size for training - larger is faster on GPU (default: from config or {default_batch_size})"
    )
    parser.add_argument(
        "--config",
        type=str,
        help="Path to config file (default: config/dev.yaml based on ENV)"
    )
    parser.add_argument(
        "--split",
        type=float,
        default=0.7,
        help="Train/test split ratio (default: 0.7)"
    )
    
    args = parser.parse_args()
    
    print("\n" + "="*60)
    print(f"🚀 AI Trading Platform - Intraday Model Training")
    print("="*60)
    print(f"Symbol: {args.symbol.upper()}")
    print(f"Timeframe: {args.timeframe}")
    print(f"Epochs: {args.epochs}")
    print(f"Batch Size: {args.batch_size} {'(GPU-optimized)' if args.batch_size >= 128 else '(small)'}")
    print(f"Train/Test Split: {args.split:.0%} / {1-args.split:.0%}")
    print("="*60 + "\n")
    
    # Initialize trainer
    trainer = IntradayTrainer(
        symbol=args.symbol,
        timeframe=args.timeframe,
    )
    
    # Load data
    try:
        features_train, features_test, target_train, target_test, data = \
            trainer.load_and_prepare_data(train_split=args.split)
    except FileNotFoundError as e:
        logger.error(str(e))
        return 1
    
    # Train models
    models = {}
    metrics = {}
    
    try:
        # Train GARCH-GRU
        garch_model, garch_metrics = trainer.train_garch_gru(
            features_train, target_train,
            features_test, target_test,
            epochs=args.epochs,
            batch_size=args.batch_size
        )
        models['garch_gru'] = garch_model
        metrics['garch_gru'] = garch_metrics
        
        # Train LSTM-Transformer
        lstm_model, lstm_metrics = trainer.train_lstm_transformer(
            features_train, target_train,
            features_test, target_test,
            epochs=args.epochs,
            batch_size=args.batch_size
        )
        models['lstm_transformer'] = lstm_model
        metrics['lstm_transformer'] = lstm_metrics
        
        # Save models
        trainer.save_models(models, metrics)
        
        print("\n" + "="*60)
        print("✅ Training Complete!")
        print("="*60)
        print(f"GARCH-GRU - MSE: {garch_metrics['mse']:.6f}, MAE: {garch_metrics['mae']:.6f}")
        print(f"LSTM-Transformer - MSE: {lstm_metrics['mse']:.6f}, MAE: {lstm_metrics['mae']:.6f}")
        print("="*60 + "\n")
        
        return 0
        
    except Exception as e:
        logger.error(f"❌ Training failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

# ============================================================
# ✅ Training Complete!
# ============================================================
# GARCH-GRU - MSE: 0.000001, MAE: 0.000672
# LSTM-Transformer - MSE: 0.000001, MAE: 0.000626
# ============================================================


# ============================================================
# ✅ Training Complete!
# ============================================================
# GARCH-GRU - MSE: 0.000001, MAE: 0.000607
# LSTM-Transformer - MSE: 0.000001, MAE: 0.000592
# ============================================================