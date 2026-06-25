"""XGBoost model for time series forecasting.

XGBoost is an optimized distributed gradient boosting library.
Known for winning many Kaggle competitions and excellent performance on financial data.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

try:
    import xgboost as xgb
except ImportError:
    xgb = None
    print("Warning: xgboost not installed. Install with: pip install xgboost")


class XGBoostModel:
    """XGBoost wrapper for trading predictions.
    
    Advantages:
    - Excellent performance on tabular/structured data
    - Built-in regularization (L1/L2)
    - Handles missing values
    - Fast training with GPU support
    - Great feature importance interpretation
    - Monotonic constraints possible (enforce logical relationships)
    """

    def __init__(
        self,
        n_estimators: int = 500,
        learning_rate: float = 0.01,
        max_depth: int = 7,
        min_child_weight: int = 1,
        subsample: float = 0.8,
        colsample_bytree: float = 0.8,
        gamma: float = 0.1,
        reg_alpha: float = 0.1,
        reg_lambda: float = 1.0,
        random_state: int = 42,
        device: Optional[str] = None,
        tree_method: str = 'auto',
    ) -> None:
        """Initialize XGBoost model.

        Args:
            n_estimators: Number of boosting rounds
            learning_rate: Step size shrinkage (eta)
            max_depth: Maximum tree depth
            min_child_weight: Minimum sum of instance weight in a child
            subsample: Row sampling ratio per iteration
            colsample_bytree: Column sampling ratio per tree
            gamma: Minimum loss reduction for split (regularization)
            reg_alpha: L1 regularization
            reg_lambda: L2 regularization
            random_state: Random seed
            device: 'cpu', 'cuda', or None for auto
            tree_method: 'auto', 'hist', 'gpu_hist'
        """
        if xgb is None:
            raise ImportError("xgboost required. Install with: pip install xgboost")
        
        self.n_estimators = n_estimators
        self.learning_rate = learning_rate
        self.max_depth = max_depth
        self.min_child_weight = min_child_weight
        self.subsample = subsample
        self.colsample_bytree = colsample_bytree
        self.gamma = gamma
        self.reg_alpha = reg_alpha
        self.reg_lambda = reg_lambda
        self.random_state = random_state
        
        # Device configuration
        if device is None or device == 'cpu':
            self.device = 'cpu'
            self.tree_method = tree_method if tree_method != 'auto' else 'hist'
        elif device in ['cuda', 'gpu']:
            self.device = 'cuda'
            self.tree_method = 'gpu_hist'  # GPU-accelerated histogram
        else:
            self.device = 'cpu'
            self.tree_method = tree_method
        
        self.model: Optional[xgb.Booster] = None
        self.feature_names: Optional[list[str]] = None
        self.feature_importances_: Optional[np.ndarray] = None
        
        # Normalization (optional)
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
            features: Feature DataFrame
            target: Target series
            validation_split: Fraction for validation
            early_stopping_rounds: Early stopping patience
            verbose: Print training progress

        Returns:
            Dictionary with training history
        """
        # Store feature names
        self.feature_names = list(features.columns)
        
        # Convert to numpy
        X = features.values
        y = target.values
        
        # Trees don't need normalization, but store for consistency
        self.feature_mean = X.mean(axis=0)
        self.feature_std = X.std(axis=0)
        
        # Train/validation split
        n_train = int(len(X) * (1 - validation_split))
        X_train, X_val = X[:n_train], X[n_train:]
        y_train, y_val = y[:n_train], y[n_train:]
        
        # Create DMatrix (XGBoost's internal data structure)
        dtrain = xgb.DMatrix(
            X_train,
            label=y_train,
            feature_names=self.feature_names,
        )
        dval = xgb.DMatrix(
            X_val,
            label=y_val,
            feature_names=self.feature_names,
        )
        
        # Parameters
        params = {
            'objective': 'reg:squarederror',
            'eval_metric': 'rmse',
            'learning_rate': self.learning_rate,
            'max_depth': self.max_depth,
            'min_child_weight': self.min_child_weight,
            'subsample': self.subsample,
            'colsample_bytree': self.colsample_bytree,
            'gamma': self.gamma,
            'reg_alpha': self.reg_alpha,
            'reg_lambda': self.reg_lambda,
            'random_state': self.random_state,
            'tree_method': self.tree_method,
            'device': self.device,
        }
        
        if verbose:
            print(f"Training XGBoost with {self.n_estimators} trees...")
            print(f"Device: {self.device}, Tree method: {self.tree_method}")
            print(f"Features: {len(self.feature_names)}")
            print(f"Training samples: {len(X_train)}, Validation: {len(X_val)}")
        
        # Evaluation list for tracking
        evals = [(dtrain, 'train'), (dval, 'valid')]
        evals_result = {}
        
        # Train model
        self.model = xgb.train(
            params,
            dtrain,
            num_boost_round=self.n_estimators,
            evals=evals,
            evals_result=evals_result,
            early_stopping_rounds=early_stopping_rounds,
            verbose_eval=max(self.n_estimators // 10, 1) if verbose else False,
        )
        
        # Extract history
        history = {
            'train_loss': evals_result['train']['rmse'],
            'val_loss': evals_result['valid']['rmse'],
        }
        
        # Store feature importances
        importance_dict = self.model.get_score(importance_type='gain')
        self.feature_importances_ = np.array([
            importance_dict.get(f, 0) for f in self.feature_names
        ])
        
        if verbose:
            print(f"\nTraining completed. Best iteration: {self.model.best_iteration}")
            print(f"Final train RMSE: {history['train_loss'][-1]:.6f}")
            print(f"Final val RMSE: {history['val_loss'][-1]:.6f}")
            
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
        dtest = xgb.DMatrix(X, feature_names=self.feature_names)
        
        predictions = self.model.predict(
            dtest,
            iteration_range=(0, self.model.best_iteration + 1)
        )
        return predictions

    def get_feature_importance(self, importance_type: str = 'gain') -> pd.DataFrame:
        """Get feature importance DataFrame.

        Args:
            importance_type: 'weight', 'gain', 'cover', 'total_gain', 'total_cover'

        Returns:
            DataFrame with feature names and importance scores
        """
        if self.model is None:
            raise ValueError("Model must be fitted first")
        
        importance_dict = self.model.get_score(importance_type=importance_type)
        importance = np.array([
            importance_dict.get(f, 0) for f in self.feature_names
        ])
        
        return pd.DataFrame({
            'feature': self.feature_names,
            'importance': importance,
        }).sort_values('importance', ascending=False)

    def save(self, path: str) -> None:
        """Save model to disk.

        Args:
            path: Path to save model
        """
        if self.model is None:
            raise ValueError("Model must be fitted before saving")
        
        path_obj = Path(path)
        
        # Save XGBoost model (JSON format)
        model_path = path_obj.with_suffix('.json')
        self.model.save_model(str(model_path))
        
        # Save metadata
        metadata = {
            'n_estimators': self.n_estimators,
            'learning_rate': self.learning_rate,
            'max_depth': self.max_depth,
            'feature_names': self.feature_names,
            'feature_mean': self.feature_mean.tolist() if self.feature_mean is not None else None,
            'feature_std': self.feature_std.tolist() if self.feature_std is not None else None,
            'best_iteration': int(self.model.best_iteration) if hasattr(self.model, 'best_iteration') else None,
        }
        
        metadata_path = path_obj.with_suffix('.meta.json')
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)

    def load(self, path: str) -> None:
        """Load model from disk.

        Args:
            path: Path to load model from
        """
        path_obj = Path(path)
        
        # Load XGBoost model
        model_path = path_obj.with_suffix('.json')
        self.model = xgb.Booster()
        self.model.load_model(str(model_path))
        
        # Load metadata
        metadata_path = path_obj.with_suffix('.meta.json')
        with open(metadata_path, 'r') as f:
            metadata = json.load(f)
        
        self.n_estimators = metadata['n_estimators']
        self.learning_rate = metadata['learning_rate']
        self.max_depth = metadata['max_depth']
        self.feature_names = metadata['feature_names']
        self.feature_mean = np.array(metadata['feature_mean']) if metadata['feature_mean'] else None
        self.feature_std = np.array(metadata['feature_std']) if metadata['feature_std'] else None
        
        # Update feature importances
        importance_dict = self.model.get_score(importance_type='gain')
        self.feature_importances_ = np.array([
            importance_dict.get(f, 0) for f in self.feature_names
        ])
