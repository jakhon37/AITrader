#!/usr/bin/env python3
"""Training script for all models.

Trains GARCH-GRU, LSTM-Transformer, ensemble, and meta-labeler models
on historical data and registers them in the model registry.
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
from features.feature_engine import FeatureEngine
from models.ensemble import EnsembleModel
from models.garch_gru import GARCHGRUModel
from models.lstm_transformer import LSTMTransformerModel
from models.meta_labeler import MetaLabeler
from models.model_registry import ModelRegistry

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ModelTrainer:
    """Orchestrates training of all models."""

    def __init__(
        self,
        config_path: str = "config/features.yaml",
        data_dir: str = "data/raw",
        registry_path: str = "models/registry",
        random_seed: int = 42,
    ) -> None:
        """Initialize trainer."""
        self.config_path = config_path
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
        else:
            logger.info("💻 Using CPU (no GPU detected)")
        
        # Initialize components
        self.feature_engine = FeatureEngine()  # Use default config
        self.registry = ModelRegistry(base_path=registry_path)
        
        logger.info(f"Initialized trainer with config: {config_path}")

    def load_and_prepare_data(
        self,
        symbol: str = "eurusd",
        train_split: float = 0.7,
    ):
        """Load and prepare training data."""
        logger.info(f"Loading data for {symbol}")
        
        # Load market data from CSV
        csv_path = self.data_dir / f"{symbol}_daily.csv"
        if not csv_path.exists():
            raise FileNotFoundError(f"Data file not found: {csv_path}")
        
        data = load_ohlcv_csv(csv_path)
        
        # Compute features
        logger.info("Computing features")
        features = self.feature_engine.compute_features(data)
        
        # Create target (future returns)
        target = data['close'].pct_change().shift(-1)
        
        # Align features and target
        valid_idx = features.dropna().index.intersection(target.dropna().index)
        features = features.loc[valid_idx]
        target = target.loc[valid_idx]
        
        # Train/test split (temporal)
        split_idx = int(len(features) * train_split)
        
        features_train = features.iloc[:split_idx]
        features_test = features.iloc[split_idx:]
        target_train = target.iloc[:split_idx]
        target_test = target.iloc[split_idx:]
        
        logger.info(f"Training samples: {len(features_train)}, Test samples: {len(features_test)}")
        
        return features_train, features_test, target_train, target_test

    def train_garch_gru(self, target_train, target_test, epochs=50, batch_size=256):
        """Train GARCH-GRU model."""
        logger.info("Training GARCH-GRU model")
        logger.info(f"   Batch size: {batch_size}")
        
        model = GARCHGRUModel(
            hidden_size=64,
            num_layers=2,
            learning_rate=0.001,
            device=str(self.device),  # Auto-detect GPU
        )
        
        history = model.fit(
            target_train,
            epochs=epochs,
            batch_size=batch_size,
            seq_length=20,
            validation_split=0.2,
            verbose=True,
        )
        
        # Evaluate
        predictions = model.predict(target_test, seq_length=20)
        actual = target_test.values[-len(predictions):]
        
        accuracy = np.mean(np.sign(predictions) == np.sign(actual))
        
        metrics = {
            'directional_accuracy': float(accuracy),
            'final_train_loss': float(history['train_loss'][-1]),
        }
        
        logger.info(f"GARCH-GRU accuracy: {accuracy:.2%}")
        
        return model, metrics

    def train_lstm_transformer(self, features_train, features_test, target_train, target_test, epochs=50, batch_size=256):
        """Train LSTM-Transformer model."""
        logger.info("Training LSTM-Transformer model")
        logger.info(f"   Batch size: {batch_size}")
        
        model = LSTMTransformerModel(
            hidden_size=128,
            num_lstm_layers=2,
            num_transformer_layers=2,
            num_heads=4,
            learning_rate=0.001,
            device=str(self.device),  # Auto-detect GPU
        )
        
        history = model.fit(
            features_train,
            target_train,
            epochs=epochs,
            batch_size=batch_size,
            seq_length=20,
            validation_split=0.2,
            verbose=True,
        )
        
        # Evaluate
        predictions = model.predict(features_test, seq_length=20)
        actual = target_test.values[-len(predictions):]
        
        accuracy = np.mean(np.sign(predictions) == np.sign(actual))
        
        metrics = {
            'directional_accuracy': float(accuracy),
            'final_train_loss': float(history['train_loss'][-1]),
        }
        
        logger.info(f"LSTM-Transformer accuracy: {accuracy:.2%}")
        
        return model, metrics

    def save_models(self, garch_gru, lstm_transformer, garch_metrics, lstm_metrics, symbol="eurusd"):
        """Save models to registry."""
        logger.info("Saving models to registry")
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Create temp directory
        temp_dir = Path("models/temp")
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        # Save GARCH-GRU
        garch_path = temp_dir / f"garch_gru_{symbol}_1d_{timestamp}.pt"
        garch_gru.save(str(garch_path))
        
        self.registry.register_model(
            model_name='garch_gru',
            model_path=garch_path,
            metadata={'metrics': garch_metrics, 'trained_at': timestamp},
            tags=['volatility', 'gru'],
        )
        
        # Save LSTM-Transformer
        lstm_path = temp_dir / f"lstm_transformer_{symbol}_1d_{timestamp}.pt"
        lstm_transformer.save(str(lstm_path))
        
        self.registry.register_model(
            model_name='lstm_transformer',
            model_path=lstm_path,
            metadata={'metrics': lstm_metrics, 'trained_at': timestamp},
            tags=['attention', 'transformer'],
        )
        
        logger.info(f"Models saved with timestamp: {timestamp}")

    def run_full_training(self, symbol="eurusd", epochs=50, batch_size=256):
        """Run full training pipeline."""
        logger.info("=" * 60)
        logger.info("Starting full training pipeline")
        logger.info("=" * 60)
        logger.info(f"Batch size: {batch_size} {'(GPU-optimized)' if batch_size >= 128 else '(small)'}")
        
        # Load data
        features_train, features_test, target_train, target_test = self.load_and_prepare_data(symbol)
        
        # Train models
        garch_gru, garch_metrics = self.train_garch_gru(
            target_train, target_test, epochs=epochs, batch_size=batch_size
        )
        lstm_transformer, lstm_metrics = self.train_lstm_transformer(
            features_train, features_test, target_train, target_test, 
            epochs=epochs, batch_size=batch_size
        )
        
        # Save models
        trainer.save_models(garch_gru, lstm_transformer, garch_metrics, lstm_metrics, symbol=symbol)
        
        # Print summary
        logger.info("=" * 60)
        logger.info("Training Complete!")
        logger.info("=" * 60)
        logger.info(f"GARCH-GRU Accuracy: {garch_metrics['directional_accuracy']:.2%}")
        logger.info(f"LSTM-Transformer Accuracy: {lstm_metrics['directional_accuracy']:.2%}")
        logger.info("=" * 60)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Train all models")
    parser.add_argument('--symbol', type=str, default='eurusd', help='Symbol to train on')
    parser.add_argument('--epochs', type=int, default=50, help='Number of epochs')
    parser.add_argument(
        '--batch-size',
        '-b',
        type=int,
        default=256,
        help='Batch size - larger is faster on GPU (default: 256, try 512-1024)'
    )
    parser.add_argument('--config', type=str, default='config/features.yaml', help='Feature config')
    parser.add_argument('--data-dir', type=str, default='data/raw', help='Data directory')
    parser.add_argument('--registry', type=str, default='models/registry', help='Model registry')
    
    args = parser.parse_args()
    
    trainer = ModelTrainer(
        config_path=args.config,
        data_dir=args.data_dir,
        registry_path=args.registry,
    )
    
    trainer.run_full_training(symbol=args.symbol, epochs=args.epochs, batch_size=args.batch_size)


if __name__ == '__main__':
    main()
