"""Config-driven feature pipeline.

The FeatureEngine orchestrates all feature extraction:
- Technical indicators
- Regime detection
- Order flow signals
- Causal validation

Maintains point-in-time guarantee to prevent future leakage.
"""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from features.technical_indicators import compute_all_indicators


class FeatureEngine:
    """Config-driven feature engineering pipeline.

    Generates features from OHLCV data while maintaining point-in-time guarantee.
    Supports caching and incremental updates.
    """

    def __init__(self, config: Optional[dict[str, Any]] = None) -> None:
        """Initialize feature engine.

        Args:
            config: Feature configuration dict with keys:
                - technical_indicators: Config for technical indicators
                - regime_detection: Enable regime detection
                - order_flow: Enable order flow signals
                - causal_validation: Enable causal validation
        """
        self.config = config or self._default_config()
        self._cache: dict[str, pd.DataFrame] = {}

    @staticmethod
    def _default_config() -> dict[str, Any]:
        """Return default feature configuration."""
        return {
            "technical_indicators": {
                "returns": [1, 5, 20],
                "volatility": {"windows": [20], "method": "std"},
                "ema": [12, 26, 50],
                "sma": [20, 50],
                "atr": [14],
                "rsi": [14],
                "macd": True,
                "bollinger": {"window": 20, "num_std": 2.0},
                "garch_inputs": {"window": 20},
            },
            "regime_detection": False,  # Phase 2 TODO
            "order_flow": False,  # Phase 2 TODO
            "causal_validation": False,  # Phase 2 TODO
        }

    def compute_features(
        self,
        df: pd.DataFrame,
        use_cache: bool = True,
    ) -> pd.DataFrame:
        """Compute all features for given OHLCV data.

        Args:
            df: OHLCV DataFrame with DatetimeIndex
            use_cache: Whether to use cached features

        Returns:
            DataFrame with all features (same index as input)

        Raises:
            ValueError: If df is not properly formatted
        """
        self._validate_input(df)

        cache_key = f"features_{id(df)}"
        if use_cache and cache_key in self._cache:
            return self._cache[cache_key]

        features = pd.DataFrame(index=df.index)

        # Technical indicators
        if "technical_indicators" in self.config:
            tech_features = compute_all_indicators(
                df, config=self.config["technical_indicators"]
            )
            features = pd.concat([features, tech_features], axis=1)

        # Regime detection (TODO: Phase 2)
        if self.config.get("regime_detection"):
            # regime_features = self._compute_regime_features(df)
            # features = pd.concat([features, regime_features], axis=1)
            pass

        # Order flow signals (TODO: Phase 2)
        if self.config.get("order_flow"):
            # flow_features = self._compute_order_flow_features(df)
            # features = pd.concat([features, flow_features], axis=1)
            pass

        if use_cache:
            self._cache[cache_key] = features

        return features

    def compute_features_at_time(
        self,
        df: pd.DataFrame,
        time: pd.Timestamp,
    ) -> pd.Series:
        """Compute features at a specific point in time (no future leakage).

        Args:
            df: Full OHLCV DataFrame
            time: Time point to compute features at

        Returns:
            Series of features at given time

        Raises:
            ValueError: If time is not in DataFrame index
        """
        if time not in df.index:
            raise ValueError(f"Time {time} not in DataFrame index")

        # Get data up to (and including) time
        df_past = df.loc[:time]

        # Compute all features
        all_features = self.compute_features(df_past, use_cache=False)

        # Return features at the specific time
        return all_features.loc[time]

    def compute_features_rolling(
        self,
        df: pd.DataFrame,
        window: int,
    ) -> pd.DataFrame:
        """Compute features using a rolling window.

        Args:
            df: OHLCV DataFrame
            window: Size of rolling window

        Returns:
            DataFrame with features computed in rolling fashion
        """
        self._validate_input(df)

        if len(df) < window:
            raise ValueError(f"DataFrame length {len(df)} < window {window}")

        features_list = []

        for i in range(window - 1, len(df)):
            window_df = df.iloc[: i + 1]
            features = self.compute_features(window_df, use_cache=False)
            features_list.append(features.iloc[-1])

        result = pd.DataFrame(features_list)
        result.index = df.index[window - 1 :]

        return result

    def validate_no_leakage(
        self,
        df: pd.DataFrame,
        features: pd.DataFrame,
        time: pd.Timestamp,
    ) -> bool:
        """Validate that features at time T only use data up to time T.

        Args:
            df: Original OHLCV DataFrame
            features: Computed features
            time: Time point to check

        Returns:
            True if no future leakage detected

        Raises:
            AssertionError: If future leakage detected
        """
        if time not in df.index or time not in features.index:
            raise ValueError(f"Time {time} not in index")

        # Recompute features using only past data
        df_past = df.loc[:time]
        features_past = self.compute_features(df_past, use_cache=False)

        # Compare with features at time T
        features_at_t = features.loc[time]
        features_past_at_t = features_past.loc[time]

        # Check if they match (allowing for small numerical errors)
        mismatch = ~pd.isna(features_at_t) & ~pd.isna(features_past_at_t) & (
            (features_at_t - features_past_at_t).abs() > 1e-10
        )

        if mismatch.any():
            raise AssertionError(
                f"Future leakage detected at {time}. "
                f"Mismatched features: {mismatch[mismatch].index.tolist()}"
            )

        return True

    def get_feature_names(self) -> list[str]:
        """Get list of all feature names that will be generated.

        Returns:
            List of feature names
        """
        # Generate with dummy data to get column names
        dummy_df = pd.DataFrame(
            {
                "open": [100.0] * 100,
                "high": [101.0] * 100,
                "low": [99.0] * 100,
                "close": [100.0] * 100,
                "volume": [1000] * 100,
            },
            index=pd.date_range("2024-01-01", periods=100, freq="D"),
        )

        features = self.compute_features(dummy_df, use_cache=False)
        return features.columns.tolist()

    def clear_cache(self) -> None:
        """Clear feature cache."""
        self._cache.clear()

    @staticmethod
    def _validate_input(df: pd.DataFrame) -> None:
        """Validate input DataFrame.

        Args:
            df: OHLCV DataFrame to validate

        Raises:
            ValueError: If DataFrame is invalid
        """
        if not isinstance(df, pd.DataFrame):
            raise ValueError("Input must be a pandas DataFrame")

        if not isinstance(df.index, pd.DatetimeIndex):
            raise ValueError("DataFrame must have DatetimeIndex")

        required_cols = ["open", "high", "low", "close"]
        missing = set(required_cols) - set(df.columns)
        if missing:
            raise ValueError(f"Missing required columns: {missing}")

        if df.empty:
            raise ValueError("DataFrame is empty")


def create_feature_engine_from_config(config_path: str) -> FeatureEngine:
    """Create FeatureEngine from YAML config file.

    Args:
        config_path: Path to YAML config file

    Returns:
        Initialized FeatureEngine
    """
    import yaml

    with open(config_path) as f:
        config = yaml.safe_load(f)

    features_config = config.get("features", {})
    return FeatureEngine(config=features_config)
