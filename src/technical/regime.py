"""Market regime detection for AITrader.

Classifies the market state (trending, ranging, volatile, unknown) based on
price action, volatility, and trend indicators.
"""

from __future__ import annotations

from typing import Optional
import numpy as np
import pandas as pd

from src.core.contracts import MarketRegime
from src.technical.indicators import compute_adx, compute_ema, compute_atr, compute_bollinger_bands


def detect_regime(df: pd.DataFrame) -> MarketRegime:
    """Detect the market regime for the latest bar in the DataFrame.

    Rules:
    - Trending: ADX > 25 AND price above/below EMA200
    - Ranging: ADX < 20 AND price within Bollinger Bands
    - Volatile: ATR > 1.5x 20-period ATR average
    - Unknown: fallback
    """
    if df.empty or len(df) < 200:  # Need at least 200 bars for EMA200
        return MarketRegime.UNKNOWN

    close = df["close"].iloc[-1]
    
    # 1. Volatile Check (ATR > 1.5x 20-period ATR average)
    # We check volatile first or in order? The D04 plan lists: Trending, Ranging, Volatile, Unknown.
    # Let's check them in a logical order, or exactly as specified.
    # Let's compute the volatility first to see if it's an extreme regime.
    atr_series = compute_atr(df, 14)
    if not atr_series.empty and len(atr_series) >= 20:
        atr_latest = atr_series.iloc[-1]
        atr_avg = atr_series.rolling(20).mean().iloc[-1]
        if not pd.isna(atr_latest) and not pd.isna(atr_avg) and atr_latest > 1.5 * atr_avg:
            return MarketRegime.VOLATILE

    # 2. Trending Check (ADX > 25 AND price above/below EMA200)
    adx_series = compute_adx(df, 14)
    ema200_series = compute_ema(df["close"], 200)
    if not adx_series.empty and not ema200_series.empty:
        adx = adx_series.iloc[-1]
        ema200 = ema200_series.iloc[-1]
        if not pd.isna(adx) and not pd.isna(ema200) and adx > 25:
            if close > ema200 or close < ema200:
                return MarketRegime.TRENDING

    # 3. Ranging Check (ADX < 20 AND price within Bollinger Bands)
    bb = compute_bollinger_bands(df["close"], 20, 2.0)
    if not adx_series.empty and not bb.empty:
        adx = adx_series.iloc[-1]
        bb_lower = bb["bb_lower"].iloc[-1]
        bb_upper = bb["bb_upper"].iloc[-1]
        if not pd.isna(adx) and not pd.isna(bb_lower) and not pd.isna(bb_upper):
            if adx < 20 and bb_lower <= close <= bb_upper:
                return MarketRegime.RANGING

    return MarketRegime.UNKNOWN


def detect_regime_series(df: pd.DataFrame) -> pd.Series:
    """Compute the regime classification for every row in the DataFrame.

    Returns a Series of MarketRegime values matching the index of df.
    """
    regimes = pd.Series(MarketRegime.UNKNOWN, index=df.index)
    if len(df) < 200:
        return regimes

    # Compute series-level components
    adx = compute_adx(df, 14)
    ema200 = compute_ema(df["close"], 200)
    atr = compute_atr(df, 14)
    atr_avg = atr.rolling(20).mean()
    bb = compute_bollinger_bands(df["close"], 20, 2.0)
    
    close = df["close"]
    bb_lower = bb["bb_lower"]
    bb_upper = bb["bb_upper"]

    # Loop from index 200 onwards to classify
    for i in range(200, len(df)):
        idx = df.index[i]
        
        # Volatile check
        if atr.iloc[i] > 1.5 * atr_avg.iloc[i]:
            regimes.iloc[i] = MarketRegime.VOLATILE
            continue
            
        # Trending check
        if adx.iloc[i] > 25 and (close.iloc[i] > ema200.iloc[i] or close.iloc[i] < ema200.iloc[i]):
            regimes.iloc[i] = MarketRegime.TRENDING
            continue
            
        # Ranging check
        if adx.iloc[i] < 20 and bb_lower.iloc[i] <= close.iloc[i] <= bb_upper.iloc[i]:
            regimes.iloc[i] = MarketRegime.RANGING
            continue

    return regimes
