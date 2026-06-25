"""Config-driven feature pipeline for offline model training (D09).

Uses D04 technical indicators; maintains point-in-time guarantee.
"""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from src.technical.indicators import compute_all_indicators


class FeatureEngine:
    """Config-driven feature engineering pipeline for training/backtest scripts."""

    def __init__(self, config: Optional[dict[str, Any]] = None) -> None:
        self.config = config or self._default_config()
        self._cache: dict[str, pd.DataFrame] = {}

    @staticmethod
    def _default_config() -> dict[str, Any]:
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
            "regime_detection": False,
            "order_flow": False,
            "causal_validation": False,
        }

    def compute_features(
        self,
        df: pd.DataFrame,
        use_cache: bool = True,
    ) -> pd.DataFrame:
        self._validate_input(df)

        cache_key = f"features_{id(df)}"
        if use_cache and cache_key in self._cache:
            return self._cache[cache_key]

        features = pd.DataFrame(index=df.index)

        if "technical_indicators" in self.config:
            tech_features = compute_all_indicators(
                df, config=self.config["technical_indicators"]
            )
            features = pd.concat([features, tech_features], axis=1)

        if use_cache:
            self._cache[cache_key] = features

        return features

    def compute_features_at_time(
        self,
        df: pd.DataFrame,
        time: pd.Timestamp,
    ) -> pd.Series:
        if time not in df.index:
            raise ValueError(f"Time {time} not in DataFrame index")

        df_past = df.loc[:time]
        all_features = self.compute_features(df_past, use_cache=False)
        return all_features.loc[time]

    def compute_features_rolling(
        self,
        df: pd.DataFrame,
        window: int,
    ) -> pd.DataFrame:
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
        if time not in df.index or time not in features.index:
            raise ValueError(f"Time {time} not in index")

        df_past = df.loc[:time]
        features_past = self.compute_features(df_past, use_cache=False)

        features_at_t = features.loc[time]
        features_past_at_t = features_past.loc[time]

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
        self._cache.clear()

    @staticmethod
    def _validate_input(df: pd.DataFrame) -> None:
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
    import yaml

    with open(config_path) as f:
        config = yaml.safe_load(f)

    features_config = config.get("features", {})
    return FeatureEngine(config=features_config)