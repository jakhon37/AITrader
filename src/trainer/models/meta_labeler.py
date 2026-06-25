"""Meta-labeler for position sizing and bet sizing.

Implements meta-labeling strategy from Advances in Financial Machine Learning
by Marcos Lopez de Prado. The meta-labeler predicts the size of the bet
rather than the side (direction), which is determined by the primary model.
"""

from __future__ import annotations

from typing import Literal, Optional

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler


class MetaLabeler:
    """Meta-labeler for determining position sizing.
    
    Takes predictions from a primary model and additional features to
    determine optimal position size (0 to 1). This helps filter out
    low-confidence predictions and scale position sizes appropriately.
    """

    def __init__(
        self,
        confidence_threshold: float = 0.55,
        n_estimators: int = 100,
        max_depth: Optional[int] = 5,
        min_samples_leaf: int = 20,
        random_state: int = 42,
    ) -> None:
        """Initialize meta-labeler.

        Args:
            confidence_threshold: Minimum confidence to take position
            n_estimators: Number of trees in random forest
            max_depth: Maximum tree depth
            min_samples_leaf: Minimum samples per leaf
            random_state: Random seed for reproducibility
        """
        self.confidence_threshold = confidence_threshold
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.min_samples_leaf = min_samples_leaf
        self.random_state = random_state
        
        # Initialize models
        self.classifier = RandomForestClassifier(
            n_estimators=n_estimators,
            max_depth=max_depth,
            min_samples_leaf=min_samples_leaf,
            random_state=random_state,
            class_weight='balanced',
        )
        
        self.scaler = StandardScaler()
        self.is_fitted = False

    def create_meta_labels(
        self,
        primary_predictions: np.ndarray,
        actual_returns: np.ndarray,
        threshold: float = 0.0,
    ) -> np.ndarray:
        """Create meta-labels for training.

        Meta-label is 1 if primary prediction was correct (profitable),
        0 if incorrect or too small to be worthwhile.

        Args:
            primary_predictions: Predictions from primary model
            actual_returns: Actual returns that occurred
            threshold: Minimum return to consider "correct"

        Returns:
            Binary array of meta-labels (1D)
        """
        # Ensure arrays are 1D
        primary_predictions = np.asarray(primary_predictions).ravel()
        actual_returns = np.asarray(actual_returns).ravel()
        
        # Check if primary prediction direction matches actual return direction
        same_sign = np.sign(primary_predictions) == np.sign(actual_returns)
        
        # Also check if return is above threshold
        sufficient_return = np.abs(actual_returns) > threshold
        
        # Meta-label is 1 if correct and sufficient
        meta_labels = (same_sign & sufficient_return).astype(int)
        
        return meta_labels

    def fit(
        self,
        features: pd.DataFrame,
        primary_predictions: np.ndarray,
        actual_returns: np.ndarray,
        return_threshold: float = 0.0,
    ) -> MetaLabeler:
        """Train the meta-labeler.

        Args:
            features: Feature DataFrame (e.g., volatility, regime, indicators)
            primary_predictions: Predictions from primary model
            actual_returns: Actual returns that occurred
            return_threshold: Minimum return to consider prediction "correct"

        Returns:
            Self for chaining
        """
        # Ensure arrays are 1D
        primary_predictions = np.asarray(primary_predictions).ravel()
        actual_returns = np.asarray(actual_returns).ravel()
        
        # Create meta-labels
        meta_labels = self.create_meta_labels(
            primary_predictions,
            actual_returns,
            return_threshold
        )
        
        # Combine features with primary prediction as additional feature
        X = features.copy()
        X['primary_pred'] = primary_predictions
        X['primary_pred_abs'] = np.abs(primary_predictions)
        
        # Scale features
        X_scaled = self.scaler.fit_transform(X)
        
        # Train classifier - ensure meta_labels is 1D
        self.classifier.fit(X_scaled, meta_labels.ravel())
        
        self.is_fitted = True
        return self

    def predict_proba(
        self,
        features: pd.DataFrame,
        primary_predictions: np.ndarray,
    ) -> np.ndarray:
        """Predict probability that primary prediction will be profitable.

        Args:
            features: Feature DataFrame
            primary_predictions: Predictions from primary model

        Returns:
            Array of probabilities (0 to 1)
        """
        if not self.is_fitted:
            raise ValueError("MetaLabeler must be fitted before prediction")
        
        # Ensure arrays are 1D
        primary_predictions = np.asarray(primary_predictions).ravel()
        
        # Combine features with primary prediction
        X = features.copy()
        X['primary_pred'] = primary_predictions
        X['primary_pred_abs'] = np.abs(primary_predictions)
        
        # Scale features
        X_scaled = self.scaler.transform(X)
        
        # Get probability of class 1 (profitable)
        probas = self.classifier.predict_proba(X_scaled)
        
        # Handle case where only one class was seen during training
        if probas.shape[1] == 1:
            # Only one class, return appropriate probability
            if self.classifier.classes_[0] == 1:
                # Only positive class seen, return high probability
                return np.ones(len(probas))
            else:
                # Only negative class seen, return low probability
                return np.zeros(len(probas))
        
        # Normal case: return probability of class 1
        return probas[:, 1]

    def predict_position_size(
        self,
        features: pd.DataFrame,
        primary_predictions: np.ndarray,
        strategy: Literal['binary', 'linear', 'quadratic'] = 'linear',
    ) -> np.ndarray:
        """Predict position sizes.

        Args:
            features: Feature DataFrame
            primary_predictions: Predictions from primary model
            strategy: How to convert probability to position size
                - binary: 0 or 1 based on threshold
                - linear: Probability directly as position size
                - quadratic: Probability squared (more conservative)

        Returns:
            Array of position sizes (0 to 1)
        """
        # Ensure arrays are 1D
        primary_predictions = np.asarray(primary_predictions).ravel()
        
        # Get probabilities
        probas = self.predict_proba(features, primary_predictions)
        
        # Convert to position sizes based on strategy
        if strategy == 'binary':
            # Binary: full size if above threshold, else zero
            sizes = (probas >= self.confidence_threshold).astype(float)
        
        elif strategy == 'linear':
            # Linear: probability as size, but zero below threshold
            sizes = np.where(
                probas >= self.confidence_threshold,
                probas,
                0.0
            )
        
        elif strategy == 'quadratic':
            # Quadratic: more conservative, penalizes lower confidence
            sizes = np.where(
                probas >= self.confidence_threshold,
                probas ** 2,
                0.0
            )
        
        else:
            raise ValueError(f"Unknown strategy: {strategy}")
        
        return sizes

    def get_signal_with_size(
        self,
        features: pd.DataFrame,
        primary_predictions: np.ndarray,
        strategy: Literal['binary', 'linear', 'quadratic'] = 'linear',
    ) -> tuple[np.ndarray, np.ndarray]:
        """Get trading signals with position sizes.

        Args:
            features: Feature DataFrame
            primary_predictions: Predictions from primary model (direction)
            strategy: Position sizing strategy

        Returns:
            Tuple of (signals, sizes)
            - signals: Direction of trade (-1, 0, 1)
            - sizes: Position size (0 to 1)
        """
        # Ensure arrays are 1D
        primary_predictions = np.asarray(primary_predictions).ravel()
        
        # Get position sizes
        sizes = self.predict_position_size(features, primary_predictions, strategy)
        
        # Convert primary predictions to signals
        signals = np.sign(primary_predictions)
        
        # Zero out signals where size is zero
        signals = signals * (sizes > 0)
        
        return signals, sizes

    def get_feature_importance(self) -> pd.Series:
        """Get feature importance from random forest.

        Returns:
            Series of feature importances
        """
        if not self.is_fitted:
            raise ValueError("MetaLabeler must be fitted before getting importance")
        
        # Get feature names from scaler
        feature_names = self.scaler.feature_names_in_
        
        importances = pd.Series(
            self.classifier.feature_importances_,
            index=feature_names
        ).sort_values(ascending=False)
        
        return importances

    def evaluate_performance(
        self,
        features: pd.DataFrame,
        primary_predictions: np.ndarray,
        actual_returns: np.ndarray,
        strategy: Literal['binary', 'linear', 'quadratic'] = 'linear',
    ) -> dict[str, float]:
        """Evaluate meta-labeler performance.

        Args:
            features: Feature DataFrame
            primary_predictions: Predictions from primary model
            actual_returns: Actual returns
            strategy: Position sizing strategy

        Returns:
            Dictionary of performance metrics
        """
        # Get signals and sizes
        signals, sizes = self.get_signal_with_size(features, primary_predictions, strategy)
        
        # Calculate returns with position sizing
        sized_returns = signals * sizes * actual_returns
        
        # Calculate metrics
        n_trades = np.sum(sizes > 0)
        avg_return = np.mean(sized_returns[sizes > 0]) if n_trades > 0 else 0
        win_rate = np.mean(sized_returns[sizes > 0] > 0) if n_trades > 0 else 0
        sharpe = (np.mean(sized_returns) / np.std(sized_returns)) * np.sqrt(252) if np.std(sized_returns) > 0 else 0
        
        # Calculate improvement vs always trading
        always_returns = np.sign(primary_predictions) * actual_returns
        always_sharpe = (np.mean(always_returns) / np.std(always_returns)) * np.sqrt(252) if np.std(always_returns) > 0 else 0
        
        return {
            'n_trades': int(n_trades),
            'n_total': len(actual_returns),
            'trade_frequency': n_trades / len(actual_returns),
            'avg_return': float(avg_return),
            'win_rate': float(win_rate),
            'sharpe_ratio': float(sharpe),
            'baseline_sharpe': float(always_sharpe),
            'sharpe_improvement': float(sharpe - always_sharpe),
        }

    def save(self, path: str) -> None:
        """Save meta-labeler to disk.

        Args:
            path: Path to save (will save as pickle)
        """
        import pickle
        
        if not self.is_fitted:
            raise ValueError("MetaLabeler must be fitted before saving")
        
        save_dict = {
            'classifier': self.classifier,
            'scaler': self.scaler,
            'confidence_threshold': self.confidence_threshold,
            'n_estimators': self.n_estimators,
            'max_depth': self.max_depth,
            'min_samples_leaf': self.min_samples_leaf,
            'random_state': self.random_state,
            'is_fitted': self.is_fitted,
        }
        
        with open(path, 'wb') as f:
            pickle.dump(save_dict, f)

    def load(self, path: str) -> None:
        """Load meta-labeler from disk.

        Args:
            path: Path to load from
        """
        import pickle
        
        with open(path, 'rb') as f:
            save_dict = pickle.load(f)
        
        self.classifier = save_dict['classifier']
        self.scaler = save_dict['scaler']
        self.confidence_threshold = save_dict['confidence_threshold']
        self.n_estimators = save_dict['n_estimators']
        self.max_depth = save_dict['max_depth']
        self.min_samples_leaf = save_dict['min_samples_leaf']
        self.random_state = save_dict['random_state']
        self.is_fitted = save_dict['is_fitted']
