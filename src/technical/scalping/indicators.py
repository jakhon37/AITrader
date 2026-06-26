"""MT4-style scalping indicators (Heiken Ashi, Hull, FL bands, JokerFilter)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.technical.indicators import compute_atr, compute_ema, compute_macd, compute_rsi
from src.technical.scalping.params import FL1_PARAMS, FL2_BASE, FL2_MULTIPLIERS, HULL_DIVISOR, HULL_PERIOD


def compute_cci(df: pd.DataFrame, period: int = 13) -> pd.Series:
    """Commodity Channel Index."""
    typical = (df["high"] + df["low"] + df["close"]) / 3.0
    sma = typical.rolling(period).mean()
    mad = typical.rolling(period).apply(
        lambda x: float(np.abs(x - x.mean()).mean()),
        raw=True,
    )
    return (typical - sma) / (0.015 * mad.replace(0.0, np.nan))


def _wma(series: pd.Series, period: int) -> pd.Series:
    period = max(2, period)

    def _apply_wma(values: np.ndarray) -> float:
        n = len(values)
        weights = np.arange(1, n + 1, dtype=float)
        return float(np.dot(values, weights) / weights.sum())

    return series.rolling(period).apply(_apply_wma, raw=True)


def compute_hull_ma(
    series: pd.Series,
    period: int = HULL_PERIOD,
    divisor: float = HULL_DIVISOR,
) -> pd.Series:
    """Hull moving average (ws_hull_lineV6 approximation)."""
    adj_period = max(2, int(round(period / divisor)))
    half = max(2, adj_period // 2)
    sqrt_p = max(2, int(round(np.sqrt(adj_period))))

    wma_half = _wma(series, half)
    wma_full = _wma(series, adj_period)
    raw = 2.0 * wma_half - wma_full
    return _wma(raw, sqrt_p)


def compute_heiken_ashi(df: pd.DataFrame) -> pd.DataFrame:
    """Heiken Ashi OHLC transform."""
    if df.empty:
        return pd.DataFrame(columns=["ha_open", "ha_high", "ha_low", "ha_close"])

    ha_close = (df["open"] + df["high"] + df["low"] + df["close"]) / 4.0
    ha_open = ha_close.copy()
    ha_open.iloc[0] = (df["open"].iloc[0] + df["close"].iloc[0]) / 2.0
    for i in range(1, len(df)):
        ha_open.iloc[i] = (ha_open.iloc[i - 1] + ha_close.iloc[i - 1]) / 2.0

    ha_high = pd.concat([df["high"], ha_open, ha_close], axis=1).max(axis=1)
    ha_low = pd.concat([df["low"], ha_open, ha_close], axis=1).min(axis=1)

    return pd.DataFrame(
        {
            "ha_open": ha_open,
            "ha_high": ha_high,
            "ha_low": ha_low,
            "ha_close": ha_close,
        },
        index=df.index,
    )


def _triangular_weights(half_length: int) -> np.ndarray:
    """Symmetric triangular kernel of length 2 * half_length + 1."""
    weights = np.concatenate(
        [
            np.arange(1, half_length + 2, dtype=float),
            np.arange(half_length, 0, -1, dtype=float),
        ]
    )
    return weights / weights.sum()


def compute_tma(series: pd.Series, half_length: int) -> pd.Series:
    """Centered triangular moving average (FL band middle line)."""
    weights = _triangular_weights(half_length)
    convolved = np.convolve(series.to_numpy(dtype=float), weights, mode="same")
    return pd.Series(convolved, index=series.index)


def compute_fl_bands(
    df: pd.DataFrame,
    half_length: int,
    atr_period: int,
    atr_multiplier: float,
) -> pd.DataFrame:
    """Floating-level ATR channel (FL1 / FL2 family)."""
    middle = compute_tma(df["close"], half_length)
    atr = compute_atr(df, atr_period)
    upper = middle + atr * atr_multiplier
    lower = middle - atr * atr_multiplier
    return pd.DataFrame(
        {
            "fl_middle": middle,
            "fl_upper": upper,
            "fl_lower": lower,
            "fl_atr": atr,
        },
        index=df.index,
    )


def compute_joker_filter(df: pd.DataFrame, smooth_period: int = 5) -> pd.Series:
    """JokerFilter approximation: smoothed directional momentum in [0, 1]."""
    momentum = df["close"].diff(3)
    smoothed = momentum.ewm(span=smooth_period, adjust=False).mean()
    rolling_std = smoothed.rolling(50, min_periods=10).std().replace(0.0, np.nan)
    z = smoothed / rolling_std
    # Sigmoid map to 0-1
    return 1.0 / (1.0 + np.exp(-z.fillna(0.0)))


def compute_tick_volume_score(df: pd.DataFrame, fast: int = 16, slow: int = 16) -> pd.Series:
    """Tick-volume style pressure: fast MA of volume vs slow MA."""
    volume = df["volume"].astype(float)
    fast_ma = volume.rolling(fast).mean()
    slow_ma = volume.rolling(slow).mean()
    ratio = (fast_ma / slow_ma.replace(0.0, np.nan)) - 1.0
    return ratio.fillna(0.0)


def compute_scalping_series(df: pd.DataFrame) -> pd.DataFrame:
    """Compute full scalping indicator series for one timeframe."""
    if df.empty or len(df) < 30:
        return pd.DataFrame(index=df.index)

    ha = compute_heiken_ashi(df)
    hull = compute_hull_ma(df["close"])
    hull_slope = hull.diff(3)
    joker = compute_joker_filter(df)
    tick_vol = compute_tick_volume_score(df)

    fl1 = compute_fl_bands(
        df,
        FL1_PARAMS.half_length,
        FL1_PARAMS.atr_period,
        FL1_PARAMS.atr_multiplier,
    )

    outer_mult = FL2_MULTIPLIERS[-1]
    fl_outer = compute_fl_bands(
        df,
        FL2_BASE.half_length,
        FL2_BASE.atr_period,
        outer_mult,
    )

    macd = compute_macd(df["close"], * (8, 21, 8))
    rsi = compute_rsi(df["close"], 8)
    cci = compute_cci(df, 13)
    ema_fast = compute_ema(df["close"], 5)
    ema_slow = compute_ema(df["close"], 7)

    close = df["close"]
    band_position = (close - fl_outer["fl_lower"]) / (
        (fl_outer["fl_upper"] - fl_outer["fl_lower"]).replace(0.0, np.nan)
    )

    return pd.DataFrame(
        {
            "ha_bullish": (ha["ha_close"] > ha["ha_open"]).astype(float),
            "hull": hull,
            "hull_slope": hull_slope,
            "joker": joker,
            "tick_vol_score": tick_vol,
            "fl1_upper": fl1["fl_upper"],
            "fl1_lower": fl1["fl_lower"],
            "fl_outer_upper": fl_outer["fl_upper"],
            "fl_outer_lower": fl_outer["fl_lower"],
            "fl_atr": fl_outer["fl_atr"],
            "band_position": band_position,
            "sb_macd_hist": macd["macd_hist"],
            "sb_rsi": rsi,
            "sb_cci": cci,
            "sb_ema_fast": ema_fast,
            "sb_ema_slow": ema_slow,
        },
        index=df.index,
    )


def latest_scalping_values(df: pd.DataFrame) -> dict[str, float]:
    """Return latest-bar scalping indicator snapshot for confluence scoring."""
    series = compute_scalping_series(df)
    if series.empty:
        return {}

    row = series.iloc[-1]
    close = float(df["close"].iloc[-1])
    atr_110 = float(row.get("fl_atr", np.nan))
    if not np.isfinite(atr_110):
        atr_110 = 0.0

    hull_slope = float(row.get("hull_slope", 0.0))
    band_pos = float(row.get("band_position", 0.5))
    if not np.isfinite(band_pos):
        band_pos = 0.5

    return {
        "close": close,
        "atr": atr_110,
        "atr_110": atr_110,
        "ha_bullish": float(row.get("ha_bullish", 0.0)),
        "hull_slope": hull_slope if np.isfinite(hull_slope) else 0.0,
        "joker": float(row.get("joker", 0.5)) if np.isfinite(row.get("joker", np.nan)) else 0.5,
        "tick_vol_score": float(row.get("tick_vol_score", 0.0)),
        "band_position": band_pos,
        "fl_outer_upper": float(row.get("fl_outer_upper", 0.0)),
        "fl_outer_lower": float(row.get("fl_outer_lower", 0.0)),
        "sb_macd_hist": float(row.get("sb_macd_hist", 0.0)),
        "sb_rsi": float(row.get("sb_rsi", 50.0)),
        "sb_cci": float(row.get("sb_cci", 0.0)),
        "sb_ema_fast": float(row.get("sb_ema_fast", 0.0)),
        "sb_ema_slow": float(row.get("sb_ema_slow", 0.0)),
    }