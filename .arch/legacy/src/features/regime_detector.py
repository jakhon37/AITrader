"""Market regime detection using Hidden Markov Models.

Detects market regimes (states) such as:
- Trending (bullish/bearish)
- Ranging/Consolidation
- High/Low volatility

Uses HMM to model hidden states based on observable features.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd
from hmmlearn import hmm


class RegimeDetector:
    """Hidden Markov Model-based regime detector.

    Detects market regimes using returns and volatility as observable features.
    """

    def __init__(
        self,
        n_regimes: int = 3,
        covariance_type: str = "full",
        n_iter: int = 100,
        random_state: Optional[int] = None,
    ) -> None:
        """Initialize regime detector.

        Args:
            n_regimes: Number of hidden states/regimes
            covariance_type: Type of covariance ('full', 'diag', 'spherical', 'tied')
            n_iter: Maximum iterations for EM algorithm
            random_state: Random seed for reproducibility
        """
        self.n_regimes = n_regimes
        self.covariance_type = covariance_type
        self.n_iter = n_iter
        self.random_state = random_state

        self.model: Optional[hmm.GaussianHMM] = None
        self._is_fitted = False

    def fit(self, df: pd.DataFrame, features: Optional[list[str]] = None) -> RegimeDetector:
        """Fit HMM on OHLCV data.

        Args:
            df: OHLCV DataFrame with DatetimeIndex
            features: List of feature column names to use. If None, uses returns and volatility.

        Returns:
            self
        """
        X = self._prepare_features(df, features)

        self.model = hmm.GaussianHMM(
            n_components=self.n_regimes,
            covariance_type=self.covariance_type,
            n_iter=self.n_iter,
            random_state=self.random_state,
        )

        self.model.fit(X)
        self._is_fitted = True

        return self

    def predict(self, df: pd.DataFrame, features: Optional[list[str]] = None) -> np.ndarray:
        """Predict regimes for given data.

        Args:
            df: OHLCV DataFrame
            features: Feature columns to use (must match fit features)

        Returns:
            Array of regime labels (0 to n_regimes-1)
        """
        if not self._is_fitted:
            raise ValueError("Model must be fitted before prediction. Call fit() first.")

        X = self._prepare_features(df, features)
        return self.model.predict(X)

    def predict_proba(
        self, df: pd.DataFrame, features: Optional[list[str]] = None
    ) -> np.ndarray:
        """Predict regime probabilities.

        Args:
            df: OHLCV DataFrame
            features: Feature columns to use

        Returns:
            Array of shape (n_samples, n_regimes) with probabilities
        """
        if not self._is_fitted:
            raise ValueError("Model must be fitted before prediction. Call fit() first.")

        X = self._prepare_features(df, features)
        return self.model.predict_proba(X)

    def get_regime_stats(self, df: pd.DataFrame, regimes: np.ndarray) -> pd.DataFrame:
        """Compute statistics for each regime.

        Args:
            df: OHLCV DataFrame
            regimes: Array of regime labels

        Returns:
            DataFrame with statistics per regime
        """
        returns = df["close"].pct_change()
        
        # Handle length mismatch (regimes may be shorter due to NaN removal in features)
        if len(regimes) < len(df):
            # Use only the last len(regimes) rows
            returns = returns.iloc[-len(regimes):]

        stats = []
        for regime in range(self.n_regimes):
            mask = regimes == regime
            if mask.sum() == 0:
                continue  # Skip regimes with no observations
                
            regime_returns = returns[mask]

            stats.append(
                {
                    "regime": regime,
                    "count": mask.sum(),
                    "mean_return": regime_returns.mean(),
                    "std_return": regime_returns.std(),
                    "sharpe": regime_returns.mean() / regime_returns.std()
                    if regime_returns.std() > 0
                    else 0,
                }
            )

        return pd.DataFrame(stats)

    def label_regimes(
        self, df: pd.DataFrame, regimes: np.ndarray
    ) -> dict[int, str]:
        """Assign human-readable labels to regimes based on characteristics.

        Args:
            df: OHLCV DataFrame
            regimes: Array of regime labels

        Returns:
            Dictionary mapping regime number to label
        """
        stats_df = self.get_regime_stats(df, regimes)

        labels = {}
        for _, row in stats_df.iterrows():
            regime = int(row["regime"])
            mean_ret = row["mean_return"]
            std_ret = row["std_return"]

            # Label based on mean return and volatility
            if mean_ret > 0.001:
                if std_ret > 0.015:
                    labels[regime] = "bullish_volatile"
                else:
                    labels[regime] = "bullish_stable"
            elif mean_ret < -0.001:
                if std_ret > 0.015:
                    labels[regime] = "bearish_volatile"
                else:
                    labels[regime] = "bearish_stable"
            else:
                if std_ret > 0.015:
                    labels[regime] = "ranging_volatile"
                else:
                    labels[regime] = "ranging_stable"

        return labels

    def _prepare_features(
        self, df: pd.DataFrame, features: Optional[list[str]] = None
    ) -> np.ndarray:
        """Prepare feature matrix for HMM.

        Args:
            df: OHLCV DataFrame
            features: Feature columns to use

        Returns:
            Feature matrix of shape (n_samples, n_features)
        """
        if features is not None:
            # Use provided features
            X = df[features].values
        else:
            # Default: returns and volatility
            returns = df["close"].pct_change()
            volatility = returns.rolling(20).std()

            X = pd.DataFrame(
                {
                    "returns": returns,
                    "volatility": volatility,
                }
            ).dropna()

            X = X.values

        # Handle NaN values
        if np.isnan(X).any():
            # Fill NaN with column means
            col_means = np.nanmean(X, axis=0)
            inds = np.where(np.isnan(X))
            X[inds] = np.take(col_means, inds[1])

        return X


def detect_regimes(
    df: pd.DataFrame,
    n_regimes: int = 3,
    random_state: Optional[int] = None,
) -> pd.Series:
    """Convenience function to detect regimes.

    Args:
        df: OHLCV DataFrame
        n_regimes: Number of regimes to detect
        random_state: Random seed

    Returns:
        Series of regime labels with same index as df
    """
    detector = RegimeDetector(n_regimes=n_regimes, random_state=random_state)
    detector.fit(df)
    regimes = detector.predict(df)

    # Pad with NaN for initial rows (due to feature calculation)
    result = pd.Series(index=df.index, dtype=float)
    result.iloc[-len(regimes) :] = regimes

    return result
