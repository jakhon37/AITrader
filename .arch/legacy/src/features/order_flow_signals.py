"""Order flow signals from volume and price action.

Provides volume-based and microstructure signals:
- Volume-weighted indicators
- Volume spikes
- On-balance volume
- Money flow index
"""

from __future__ import annotations

import pandas as pd


def compute_volume_ratio(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """Compute volume ratio (current / rolling average).

    Args:
        df: OHLCV DataFrame
        window: Rolling window size

    Returns:
        Series of volume ratios
    """
    avg_volume = df["volume"].rolling(window=window).mean()
    return df["volume"] / avg_volume


def compute_obv(df: pd.DataFrame) -> pd.Series:
    """Compute On-Balance Volume.

    Args:
        df: OHLCV DataFrame

    Returns:
        Series of OBV values
    """
    obv = (df["close"].diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0)) * df["volume"]).cumsum()
    return obv


def compute_vwap(df: pd.DataFrame) -> pd.Series:
    """Compute Volume-Weighted Average Price.

    Args:
        df: OHLCV DataFrame with intraday data

    Returns:
        Series of VWAP values
    """
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    return (typical_price * df["volume"]).cumsum() / df["volume"].cumsum()


def compute_mfi(df: pd.DataFrame, window: int = 14) -> pd.Series:
    """Compute Money Flow Index.

    Args:
        df: OHLCV DataFrame
        window: Window size

    Returns:
        Series of MFI values (0-100)
    """
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    money_flow = typical_price * df["volume"]

    # Positive and negative money flow
    positive_flow = money_flow.where(typical_price > typical_price.shift(1), 0)
    negative_flow = money_flow.where(typical_price < typical_price.shift(1), 0)

    positive_mf = positive_flow.rolling(window=window).sum()
    negative_mf = negative_flow.rolling(window=window).sum()

    mfi = 100 - (100 / (1 + positive_mf / negative_mf))
    return mfi


def compute_volume_spike(df: pd.DataFrame, window: int = 20, threshold: float = 2.0) -> pd.Series:
    """Detect volume spikes.

    Args:
        df: OHLCV DataFrame
        window: Rolling window for average
        threshold: Multiplier for spike detection

    Returns:
        Binary series (1 = spike, 0 = normal)
    """
    vol_ratio = compute_volume_ratio(df, window)
    return (vol_ratio > threshold).astype(int)


def compute_all_order_flow_signals(df: pd.DataFrame) -> pd.DataFrame:
    """Compute all order flow signals.

    Args:
        df: OHLCV DataFrame

    Returns:
        DataFrame with all order flow signals
    """
    signals = pd.DataFrame(index=df.index)

    signals["volume_ratio"] = compute_volume_ratio(df)
    signals["obv"] = compute_obv(df)
    signals["vwap"] = compute_vwap(df)
    signals["mfi"] = compute_mfi(df)
    signals["volume_spike"] = compute_volume_spike(df)

    return signals
