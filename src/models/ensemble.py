"""Ensemble model that combines predictions from multiple models.

Supports different combination strategies including weighted voting, averaging,
stacking, and dynamic weighting based on recent performance.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, Optional

import numpy as np
import pandas as pd


class EnsembleModel:
    """Ensemble model for combining predictions from multiple base models.
    
    Supports multiple combination strategies:
    - weighted_average: Weighted average of predictions
    - simple_average: Simple average of predictions
    - median: Median of predictions
    - voting: Majority voting (for classification)
    - dynamic: Dynamic weighting based on recent performance
    """

    def __init__(
        self,
        models: Optional[list[Any]] = None,
        weights: Optional[list[float]] = None,
        strategy: Literal[
            'weighted_average',
            'simple_average',
            'median',
            'voting',
            'dynamic'
        ] = 'weighted_average',
        dynamic_window: int = 50,
    ) -> None:
        """Initialize ensemble model.

        Args:
            models: List of base models (must have predict() method)
            weights: Weights for each model (for weighted_average strategy)
            strategy: Combination strategy
            dynamic_window: Window size for dynamic weighting
        """
        self.models = models or []
        self.strategy = strategy
        self.dynamic_window = dynamic_window
        
        # Set weights
        if weights is not None:
            if len(weights) != len(self.models):
                raise ValueError("Number of weights must match number of models")
            if not np.isclose(sum(weights), 1.0):
                raise ValueError("Weights must sum to 1.0")
            self.weights = np.array(weights)
        else:
            # Equal weights by default
            n_models = len(self.models)
            self.weights = np.ones(n_models) / n_models if n_models > 0 else np.array([])
        
        # For dynamic weighting
        self.recent_errors: list[list[float]] = [[] for _ in self.models]

    def add_model(self, model: Any, weight: Optional[float] = None) -> None:
        """Add a model to the ensemble.

        Args:
            model: Model to add (must have predict() method)
            weight: Optional weight for the model
        """
        if not hasattr(model, 'predict'):
            raise ValueError("Model must have a predict() method")
        
        self.models.append(model)
        self.recent_errors.append([])
        
        # Recalculate weights
        if weight is not None:
            # Add weight and renormalize
            new_weights = list(self.weights) + [weight]
            self.weights = np.array(new_weights) / sum(new_weights)
        else:
            # Equal weights
            n_models = len(self.models)
            self.weights = np.ones(n_models) / n_models

    def remove_model(self, index: int) -> None:
        """Remove a model from the ensemble.

        Args:
            index: Index of model to remove
        """
        if index < 0 or index >= len(self.models):
            raise ValueError(f"Invalid model index: {index}")
        
        self.models.pop(index)
        self.recent_errors.pop(index)
        
        # Recalculate weights
        self.weights = np.delete(self.weights, index)
        if len(self.weights) > 0:
            self.weights = self.weights / self.weights.sum()

    def _get_dynamic_weights(self) -> np.ndarray:
        """Calculate dynamic weights based on recent performance.

        Returns:
            Array of weights based on inverse of recent errors
        """
        if not any(self.recent_errors):
            # No error history, use equal weights
            return np.ones(len(self.models)) / len(self.models)
        
        # Calculate average recent error for each model
        avg_errors = []
        for errors in self.recent_errors:
            if len(errors) > 0:
                # Use recent window
                recent = errors[-self.dynamic_window:]
                avg_errors.append(np.mean(np.abs(recent)))
            else:
                # No errors yet, use neutral value
                avg_errors.append(1.0)
        
        avg_errors = np.array(avg_errors)
        
        # Inverse error weighting (lower error = higher weight)
        # Add small epsilon to avoid division by zero
        weights = 1.0 / (avg_errors + 1e-8)
        
        # Normalize
        weights = weights / weights.sum()
        
        return weights

    def predict(
        self,
        X: pd.DataFrame | np.ndarray,
        **kwargs: Any,
    ) -> np.ndarray:
        """Make ensemble predictions.

        Args:
            X: Input features
            **kwargs: Additional arguments passed to base models

        Returns:
            Array of ensemble predictions
        """
        if len(self.models) == 0:
            raise ValueError("No models in ensemble")
        
        # Get predictions from all models
        predictions = []
        for model in self.models:
            pred = model.predict(X, **kwargs)
            predictions.append(pred)
        
        # Ensure all predictions have the same length
        pred_lengths = [len(p) for p in predictions]
        if len(set(pred_lengths)) > 1:
            # Take minimum length
            min_length = min(pred_lengths)
            predictions = [p[:min_length] for p in predictions]
        
        predictions = np.array(predictions)
        
        # Combine predictions based on strategy
        if self.strategy == 'weighted_average':
            # Weighted average
            ensemble_pred = np.average(predictions, axis=0, weights=self.weights)
        
        elif self.strategy == 'simple_average':
            # Simple average
            ensemble_pred = np.mean(predictions, axis=0)
        
        elif self.strategy == 'median':
            # Median
            ensemble_pred = np.median(predictions, axis=0)
        
        elif self.strategy == 'voting':
            # Majority voting (for classification)
            # Convert to binary signals
            binary_preds = (predictions > 0).astype(int)
            ensemble_pred = np.mean(binary_preds, axis=0)
        
        elif self.strategy == 'dynamic':
            # Dynamic weighting based on recent performance
            weights = self._get_dynamic_weights()
            ensemble_pred = np.average(predictions, axis=0, weights=weights)
        
        else:
            raise ValueError(f"Unknown strategy: {self.strategy}")
        
        return ensemble_pred

    def update_errors(self, predictions: list[np.ndarray], actual: np.ndarray) -> None:
        """Update error history for dynamic weighting.

        Args:
            predictions: List of predictions from each model
            actual: Actual values
        """
        if len(predictions) != len(self.models):
            raise ValueError("Number of predictions must match number of models")
        
        # Calculate errors for each model
        for i, pred in enumerate(predictions):
            errors = pred - actual
            self.recent_errors[i].extend(errors.tolist())
            
            # Keep only recent window
            if len(self.recent_errors[i]) > self.dynamic_window * 2:
                self.recent_errors[i] = self.recent_errors[i][-self.dynamic_window:]

    def get_model_weights(self) -> dict[int, float]:
        """Get current model weights.

        Returns:
            Dictionary mapping model index to weight
        """
        if self.strategy == 'dynamic':
            weights = self._get_dynamic_weights()
        else:
            weights = self.weights
        
        return {i: float(w) for i, w in enumerate(weights)}

    def get_predictions_with_confidence(
        self,
        X: pd.DataFrame | np.ndarray,
        **kwargs: Any,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Get predictions with confidence estimates.

        Args:
            X: Input features
            **kwargs: Additional arguments passed to base models

        Returns:
            Tuple of (predictions, confidence_scores)
            Confidence based on agreement between models
        """
        if len(self.models) == 0:
            raise ValueError("No models in ensemble")
        
        # Get predictions from all models
        predictions = []
        for model in self.models:
            pred = model.predict(X, **kwargs)
            predictions.append(pred)
        
        # Ensure same length
        pred_lengths = [len(p) for p in predictions]
        if len(set(pred_lengths)) > 1:
            min_length = min(pred_lengths)
            predictions = [p[:min_length] for p in predictions]
        
        predictions = np.array(predictions)
        
        # Calculate ensemble prediction
        ensemble_pred = self.predict(X, **kwargs)
        
        # Calculate confidence as inverse of std dev (agreement between models)
        std_dev = np.std(predictions, axis=0)
        
        # Normalize to [0, 1] range (lower std = higher confidence)
        # Use sigmoid-like transformation
        confidence = 1.0 / (1.0 + std_dev)
        
        return ensemble_pred, confidence

    def save(self, path: str) -> None:
        """Save ensemble configuration.

        Note: This saves only the ensemble config, not the base models.
        Base models should be saved separately.

        Args:
            path: Path to save configuration
        """
        import json
        
        config = {
            'strategy': self.strategy,
            'weights': self.weights.tolist(),
            'dynamic_window': self.dynamic_window,
            'n_models': len(self.models),
            'recent_errors': self.recent_errors,
        }
        
        with open(path, 'w') as f:
            json.dump(config, f, indent=2)

    def load(self, path: str) -> None:
        """Load ensemble configuration.

        Note: This loads only the ensemble config, not the base models.
        Base models should be loaded separately and added with add_model().

        Args:
            path: Path to load configuration from
        """
        import json
        
        with open(path, 'r') as f:
            config = json.load(f)
        
        self.strategy = config['strategy']
        self.weights = np.array(config['weights'])
        self.dynamic_window = config['dynamic_window']
        self.recent_errors = config['recent_errors']
        
        # Models need to be added separately

    def get_diversity_score(self, X: pd.DataFrame | np.ndarray, **kwargs: Any) -> float:
        """Calculate diversity score of ensemble predictions.

        Higher diversity means models are making different predictions,
        which can be beneficial for ensemble performance.

        Args:
            X: Input features
            **kwargs: Additional arguments passed to base models

        Returns:
            Diversity score (average pairwise correlation between predictions)
        """
        if len(self.models) < 2:
            return 0.0
        
        # Get predictions from all models
        predictions = []
        for model in self.models:
            pred = model.predict(X, **kwargs)
            predictions.append(pred)
        
        # Ensure same length
        pred_lengths = [len(p) for p in predictions]
        if len(set(pred_lengths)) > 1:
            min_length = min(pred_lengths)
            predictions = [p[:min_length] for p in predictions]
        
        predictions = np.array(predictions)
        
        # Calculate pairwise correlations
        n_models = len(predictions)
        correlations = []
        
        for i in range(n_models):
            for j in range(i + 1, n_models):
                corr = np.corrcoef(predictions[i], predictions[j])[0, 1]
                if not np.isnan(corr):
                    correlations.append(corr)
        
        # Average correlation (lower = more diverse)
        if len(correlations) > 0:
            avg_corr = np.mean(correlations)
            # Return diversity score (1 - correlation)
            return 1.0 - avg_corr
        else:
            return 0.0
