"""LightGBM model for time series forecasting.

LightGBM is a gradient boosting framework that uses tree-based learning.
It's fast, efficient, and often outperforms neural networks on tabular data.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

try:
    import lightgbm as lgb
except ImportError:
    lgb = None
    print("Warning: lightgbm not installed. Install with: pip install lightgbm")


class LightGBMModel:
    """LightGBM wrapper for trading predictions.
    
    Advantages over neural networks:
    - No sequence preparation needed (uses raw features)
    - Faster training (typically 10-100x faster)
    - Better feature importance interpretation
    - Less prone to overfitting
    - Handles missing values naturally
    - No GPU required (but can use GPU if available)
    """

    def __init__(
        self,
        n_estimators: int = 500,
        learning_rate: float = 0.01,
        max_depth: int = 7,
        num_leaves: int = 127,
        min_child_samples: int = 20,
        subsample: float = 0.8,
        colsample_bytree: float = 0.8,
        reg_alpha: float = 0.1,
        reg_lambda: float = 0.1,
        random_state: int = 42,
        device: Optional[str] = None,
        verbose: int = -1,
    ) -> None:
        """Initialize LightGBM model.

        Args:
            n_estimators: Number of boosting iterations (trees)
            learning_rate: Learning rate (lower = slower but more robust)
            max_depth: Maximum tree depth (prevents overfitting)
            num_leaves: Maximum number of leaves per tree
            min_child_samples: Minimum samples in a leaf
            subsample: Row sampling ratio per iteration
            colsample_bytree: Column sampling ratio per tree
            reg_alpha: L1 regularization
            reg_lambda: L2 regularization
            random_state: Random seed
            device: 'cpu', 'gpu', or None for auto
            verbose: Verbosity level (-1 = silent)
        """
        if lgb is None:
            raise ImportError("lightgbm required. Install with: pip install lightgbm")
        
        self.n_estimators = n_estimators
        self.learning_rate = learning_rate
        self.max_depth = max_depth
        self.num_leaves = num_leaves
        self.min_child_samples = min_child_samples
        self.subsample = subsample
        self.colsample_bytree = colsample_bytree
        self.reg_alpha = reg_alpha
        self.reg_lambda = reg_lambda
        self.random_state = random_state
        self.verbose = verbose
        
        # Auto-detect device
        if device is None or device == 'cpu':
            self.device_type = 'cpu'
        elif device in ['cuda', 'gpu']:
            self.device_type = 'gpu'
        else:
            self.device_type = 'cpu'
        
        self.model: Optional[lgb.Booster] = None
        self.feature_names: Optional[list[str]] = None
        self.feature_importances_: Optional[np.ndarray] = None
        
        # Normalization (optional for trees, but helps)
        self.feature_mean: Optional[np.ndarray] = None
        self.feature_std: Optional[np.ndarray] = None

    def fit(
        self,
        features: pd.DataFrame,
        target: pd.Series,
        validation_split: float = 0.2,
        early_stopping_rounds: int = 50,
        verbose: bool = True,
    ) -> dict[str, list[float]]:
        """Train the model.

        Args:
            features: Feature DataFrame (no sequences needed!)
            target: Target series (e.g., future returns)
            validation_split: Fraction for validation
            early_stopping_rounds: Stop if no improvement for N rounds
            verbose: Print training progress

        Returns:
            Dictionary with training history
        """
        # Store feature names
        self.feature_names = list(features.columns)
        
        # Convert to numpy
        X = features.values
        y = target.values
        
        # Optional: Normalize features (not required for trees but can help)
        self.feature_mean = X.mean(axis=0)
        self.feature_std = X.std(axis=0)
        # X_norm = (X - self.feature_mean) / (self.feature_std + 1e-8)
        # For trees, normalization usually not needed - skip it
        X_norm = X
        
        # Train/validation split
        n_train = int(len(X_norm) * (1 - validation_split))
        X_train, X_val = X_norm[:n_train], X_norm[n_train:]
        y_train, y_val = y[:n_train], y[n_train:]
        
        # Create LightGBM datasets
        train_data = lgb.Dataset(
            X_train, 
            label=y_train,
            feature_name=self.feature_names,
        )
        val_data = lgb.Dataset(
            X_val,
            label=y_val,
            feature_name=self.feature_names,
            reference=train_data,
        )
        
        # Parameters
        params = {
            'objective': 'regression',
            'metric': 'mse',
            'boosting_type': 'gbdt',
            'learning_rate': self.learning_rate,
            'max_depth': self.max_depth,
            'num_leaves': self.num_leaves,
            'min_child_samples': self.min_child_samples,
            'subsample': self.subsample,
            'colsample_bytree': self.colsample_bytree,
            'reg_alpha': self.reg_alpha,
            'reg_lambda': self.reg_lambda,
            'random_state': self.random_state,
            'device_type': self.device_type,
            'verbose': self.verbose,
        }
        
        # Callbacks for tracking
        history = {'train_loss': [], 'val_loss': []}
        
        def callback(env):
            """Custom callback to store history."""
            train_loss = env.evaluation_result_list[0][2] if env.evaluation_result_list else 0
            val_loss = env.evaluation_result_list[1][2] if len(env.evaluation_result_list) > 1 else 0
            history['train_loss'].append(train_loss)
            history['val_loss'].append(val_loss)
        
        # Train model
        if verbose:
            print(f"Training LightGBM with {self.n_estimators} trees...")
            print(f"Device: {self.device_type}")
            print(f"Features: {len(self.feature_names)}")
            print(f"Training samples: {len(X_train)}, Validation: {len(X_val)}")
        
        self.model = lgb.train(
            params,
            train_data,
            num_boost_round=self.n_estimators,
            valid_sets=[train_data, val_data],
            valid_names=['train', 'valid'],
            callbacks=[
                callback,
                lgb.early_stopping(early_stopping_rounds, verbose=verbose),
                lgb.log_evaluation(period=max(self.n_estimators // 10, 1), show_stdv=False) if verbose else None,
            ],
        )
        
        # Store feature importances
        self.feature_importances_ = self.model.feature_importance(importance_type='gain')
        
        if verbose:
            print(f"\nTraining completed. Best iteration: {self.model.best_iteration}")
            print(f"Final train loss: {history['train_loss'][-1]:.6f}")
            print(f"Final val loss: {history['val_loss'][-1]:.6f}")
            
            # Show top 10 important features
            if self.feature_names is not None:
                importance_df = pd.DataFrame({
                    'feature': self.feature_names,
                    'importance': self.feature_importances_
                }).sort_values('importance', ascending=False)
                print("\nTop 10 most important features:")
                print(importance_df.head(10).to_string(index=False))
        
        return history

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        """Make predictions.

        Args:
            features: Feature DataFrame

        Returns:
            Array of predictions
        """
        if self.model is None:
            raise ValueError("Model must be fitted before prediction")
        
        X = features.values
        # X_norm = (X - self.feature_mean) / (self.feature_std + 1e-8)
        X_norm = X  # No normalization for trees
        
        predictions = self.model.predict(X_norm, num_iteration=self.model.best_iteration)
        return predictions

    def get_feature_importance(self, importance_type: str = 'gain') -> pd.DataFrame:
        """Get feature importance DataFrame.

        Args:
            importance_type: 'gain', 'split', or 'weight'

        Returns:
            DataFrame with feature names and importance scores
        """
        if self.model is None:
            raise ValueError("Model must be fitted first")
        
        importance = self.model.feature_importance(importance_type=importance_type)
        
        return pd.DataFrame({
            'feature': self.feature_names,
            'importance': importance,
        }).sort_values('importance', ascending=False)

    def save(self, path: str) -> None:
        """Save model to disk.

        Args:
            path: Path to save model (will save as .txt for LightGBM)
        """
        if self.model is None:
            raise ValueError("Model must be fitted before saving")
        
        path_obj = Path(path)
        
        # Save LightGBM model (native format)
        model_path = path_obj.with_suffix('.txt')
        self.model.save_model(str(model_path))
        
        # Save metadata
        metadata = {
            'n_estimators': self.n_estimators,
            'learning_rate': self.learning_rate,
            'max_depth': self.max_depth,
            'num_leaves': self.num_leaves,
            'feature_names': self.feature_names,
            'feature_mean': self.feature_mean.tolist() if self.feature_mean is not None else None,
            'feature_std': self.feature_std.tolist() if self.feature_std is not None else None,
        }
        
        metadata_path = path_obj.with_suffix('.json')
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)

    def load(self, path: str) -> None:
        """Load model from disk.

        Args:
            path: Path to load model from
        """
        path_obj = Path(path)
        
        # Load LightGBM model
        model_path = path_obj.with_suffix('.txt')
        self.model = lgb.Booster(model_file=str(model_path))
        
        # Load metadata
        metadata_path = path_obj.with_suffix('.json')
        with open(metadata_path, 'r') as f:
            metadata = json.load(f)
        
        self.n_estimators = metadata['n_estimators']
        self.learning_rate = metadata['learning_rate']
        self.max_depth = metadata['max_depth']
        self.num_leaves = metadata['num_leaves']
        self.feature_names = metadata['feature_names']
        self.feature_mean = np.array(metadata['feature_mean']) if metadata['feature_mean'] else None
        self.feature_std = np.array(metadata['feature_std']) if metadata['feature_std'] else None
        
        # Update feature importances
        self.feature_importances_ = self.model.feature_importance(importance_type='gain')
