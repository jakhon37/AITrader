"""Order flow and volume signals for AITrader.

Provides volume-based and microstructure signals.
Requires volume data.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def compute_volume_ratio(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """Compute volume ratio (current / rolling average)."""
    avg_volume = df["volume"].rolling(window=window).mean()
    return df["volume"] / avg_volume.replace(0.0, np.nan)


def compute_obv(df: pd.DataFrame) -> pd.Series:
    """Compute On-Balance Volume."""
    close_diff = df["close"].diff()
    direction = np.sign(close_diff).fillna(0.0)
    obv = (direction * df["volume"]).cumsum()
    return obv


def compute_vwap(df: pd.DataFrame) -> pd.Series:
    """Compute Volume-Weighted Average Price."""
    typical_price = (df["high"] + df["low"] + df["close"]) / 3.0
    return (typical_price * df["volume"]).cumsum() / df["volume"].cumsum().replace(0.0, np.nan)


def compute_mfi(df: pd.DataFrame, window: int = 14) -> pd.Series:
    """Compute Money Flow Index (0-100)."""
    typical_price = (df["high"] + df["low"] + df["close"]) / 3.0
    money_flow = typical_price * df["volume"]

    typical_price_shift = typical_price.shift(1)
    positive_flow = money_flow.where(typical_price > typical_price_shift, 0.0)
    negative_flow = money_flow.where(typical_price < typical_price_shift, 0.0)

    positive_mf = positive_flow.rolling(window=window).sum()
    negative_mf = negative_flow.rolling(window=window).sum()

    mfi = 100 - (100 / (1 + positive_mf / negative_mf.replace(0.0, np.nan)))
    return mfi.fillna(50.0)


def compute_volume_spike(df: pd.DataFrame, window: int = 20, threshold: float = 2.0) -> pd.Series:
    """Detect volume spikes."""
    vol_ratio = compute_volume_ratio(df, window)
    return (vol_ratio > threshold).astype(int)


def compute_all_order_flow_signals(df: pd.DataFrame) -> pd.DataFrame:
    """Compute all order flow signals."""
    features = pd.DataFrame(index=df.index)
    if df.empty or "volume" not in df.columns or (df["volume"] == 0.0).all():
        # Fallback to zeros if no volume data is present
        features["volume_ratio"] = 1.0
        features["obv"] = 0.0
        features["vwap"] = df["close"] if not df.empty else 0.0
        features["mfi"] = 50.0
        features["volume_spike"] = 0
        return features

    features["volume_ratio"] = compute_volume_ratio(df)
    features["obv"] = compute_obv(df)
    features["vwap"] = compute_vwap(df).fillna(df["close"])
    features["mfi"] = compute_mfi(df)
    features["volume_spike"] = compute_volume_spike(df)
    return features
