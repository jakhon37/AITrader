"""Technical indicators for feature engineering and technical signal generation.

Provides functions to compute standard technical indicators on a DataFrame.
Includes multi-timeframe computation helper.
"""

from __future__ import annotations

from typing import Any, Optional
import numpy as np
import pandas as pd

from src.core.contracts import Timeframe


def compute_returns(
    df: pd.DataFrame,
    price_col: str = "close",
    periods: int = 1,
    log_returns: bool = False,
) -> pd.Series:
    """Compute simple or log returns."""
    prices = df[price_col]
    if log_returns:
        return np.log(prices / prices.shift(periods))
    return prices.pct_change(periods=periods)


def compute_volatility(
    df: pd.DataFrame,
    window: int = 20,
    method: str = "std",
    price_col: str = "close",
) -> pd.Series:
    """Compute rolling volatility."""
    if method == "std":
        returns = compute_returns(df, price_col=price_col, log_returns=True)
        return returns.rolling(window).std() * np.sqrt(252)  # Annualized

    elif method == "parkinson":
        hl = np.log(df["high"] / df["low"])
        return (hl**2 / (4 * np.log(2))).rolling(window).mean().apply(np.sqrt) * np.sqrt(252)

    elif method == "garman_klass":
        hl = np.log(df["high"] / df["low"]) ** 2
        co = np.log(df["close"] / df["open"]) ** 2
        gk = 0.5 * hl - (2 * np.log(2) - 1) * co
        return gk.rolling(window).mean().apply(np.sqrt) * np.sqrt(252)

    else:
        raise ValueError(f"Unknown volatility method: {method}")


def compute_ema(series: pd.Series, span: int) -> pd.Series:
    """Compute Exponential Moving Average."""
    return series.ewm(span=span, adjust=False).mean()


def compute_sma(series: pd.Series, window: int) -> pd.Series:
    """Compute Simple Moving Average."""
    return series.rolling(window=window).mean()


def compute_atr(df: pd.DataFrame, window: int = 14) -> pd.Series:
    """Compute Average True Range."""
    high = df["high"]
    low = df["low"]
    close_prev = df["close"].shift(1)

    tr1 = high - low
    tr2 = (high - close_prev).abs()
    tr3 = (low - close_prev).abs()

    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return true_range.rolling(window=window).mean()


def compute_rsi(series: pd.Series, window: int = 14) -> pd.Series:
    """Compute Relative Strength Index."""
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()

    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def compute_macd(
    series: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pd.DataFrame:
    """Compute MACD."""
    ema_fast = compute_ema(series, fast)
    ema_slow = compute_ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = compute_ema(macd_line, signal)
    histogram = macd_line - signal_line

    return pd.DataFrame(
        {
            "macd": macd_line,
            "macd_signal": signal_line,
            "macd_hist": histogram,
        }
    )


def compute_bollinger_bands(
    series: pd.Series,
    window: int = 20,
    num_std: float = 2.0,
) -> pd.DataFrame:
    """Compute Bollinger Bands."""
    middle = compute_sma(series, window)
    std = series.rolling(window=window).std()

    upper = middle + (std * num_std)
    lower = middle - (std * num_std)
    width = (upper - lower) / middle

    return pd.DataFrame(
        {
            "bb_middle": middle,
            "bb_upper": upper,
            "bb_lower": lower,
            "bb_width": width,
        }
    )


def compute_garch_inputs(
    df: pd.DataFrame,
    window: int = 20,
    price_col: str = "close",
) -> pd.DataFrame:
    """Compute GARCH-related input features."""
    returns = compute_returns(df, price_col=price_col, log_returns=True)

    ret_mean = returns.rolling(window).mean()
    ret_std = returns.rolling(window).std()
    ret_skew = returns.rolling(window).skew()
    ret_kurt = returns.rolling(window).kurt()
    ret_squared = returns**2
    arch_lag1 = ret_squared.shift(1)

    return pd.DataFrame(
        {
            "ret_mean": ret_mean,
            "ret_std": ret_std,
            "ret_skew": ret_skew,
            "ret_kurt": ret_kurt,
            "ret_squared": ret_squared,
            "arch_lag1": arch_lag1,
        }
    )


def compute_adx(df: pd.DataFrame, window: int = 14) -> pd.Series:
    """Compute Average Directional Index (ADX)."""
    high = df["high"]
    low = df["low"]
    close = df["close"]
    close_prev = close.shift(1)

    tr1 = high - low
    tr2 = (high - close_prev).abs()
    tr3 = (low - close_prev).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    up_move = high - high.shift(1)
    down_move = low.shift(1) - low

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    tr_smooth = pd.Series(tr).ewm(alpha=1/window, adjust=False).mean()
    plus_dm_smooth = pd.Series(plus_dm, index=df.index).ewm(alpha=1/window, adjust=False).mean()
    minus_dm_smooth = pd.Series(minus_dm, index=df.index).ewm(alpha=1/window, adjust=False).mean()

    plus_di = 100 * (plus_dm_smooth / tr_smooth)
    minus_di = 100 * (minus_dm_smooth / tr_smooth)

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).fillna(1.0)
    adx = dx.ewm(alpha=1/window, adjust=False).mean()

    return adx


def compute_stochastic(df: pd.DataFrame, window: int = 14, smooth_k: int = 3) -> pd.DataFrame:
    """Compute Stochastic Oscillator (%K and %D)."""
    high = df["high"]
    low = df["low"]
    close = df["close"]

    lowest_low = low.rolling(window=window).min()
    highest_high = high.rolling(window=window).max()

    k = 100 * (close - lowest_low) / (highest_high - lowest_low).replace(0.0, np.nan)
    k = k.fillna(50.0)

    d = k.rolling(window=smooth_k).mean()

    return pd.DataFrame({"stoch_k": k, "stoch_d": d}, index=df.index)


def compute_obv(df: pd.DataFrame) -> pd.Series:
    """Compute On-Balance Volume (OBV)."""
    close = df["close"]
    volume = df["volume"]
    ret = close.diff()
    direction = np.sign(ret).fillna(0.0)
    obv = (volume * direction).cumsum()
    return obv


def compute_vwap(df: pd.DataFrame) -> pd.Series:
    """Compute Volume Weighted Average Price (VWAP)."""
    close = df["close"]
    volume = df["volume"]
    typical_price = (df["high"] + df["low"] + close) / 3.0

    if isinstance(df.index, pd.DatetimeIndex):
        tp_v = typical_price * volume
        cum_tp_v = tp_v.groupby(df.index.date).cumsum()
        cum_v = volume.groupby(df.index.date).cumsum()
        vwap = cum_tp_v / cum_v.replace(0.0, np.nan)
    else:
        vwap = (typical_price * volume).cumsum() / volume.cumsum().replace(0.0, np.nan)

    return vwap.fillna(close)


def compute_swing_pivots(df: pd.DataFrame, window: int = 3) -> pd.DataFrame:
    """Find swing highs and swing lows."""
    high = df["high"]
    low = df["low"]

    rolling_high = high.rolling(window=2 * window + 1, center=True).max()
    rolling_low = low.rolling(window=2 * window + 1, center=True).min()

    swing_high = high.where(high == rolling_high)
    swing_low = low.where(low == rolling_low)

    return pd.DataFrame({"swing_high": swing_high, "swing_low": swing_low}, index=df.index)


def compute_sr_distance(df: pd.DataFrame, window: int = 3) -> pd.DataFrame:
    """Compute distance to nearest support and resistance from swing pivots."""
    pivots = compute_swing_pivots(df, window=window)
    close = df["close"]

    support = pivots["swing_low"].ffill()
    resistance = pivots["swing_high"].ffill()

    dist_support = close - support
    dist_resistance = resistance - close

    return pd.DataFrame(
        {
            "support": support,
            "resistance": resistance,
            "dist_support": dist_support,
            "dist_resistance": dist_resistance,
        },
        index=df.index,
    )


def compute_all_indicators(
    df: pd.DataFrame,
    config: Optional[dict] = None,
) -> pd.DataFrame:
    """Compute all technical indicators based on config. Used for backward compatibility."""
    if config is None:
        config = {
            "returns": [1, 5, 20],
            "volatility": {"windows": [20, 60], "method": "std"},
            "ema": [12, 26, 50, 200],
            "sma": [20, 50, 200],
            "atr": [14],
            "rsi": [14],
            "macd": True,
            "bollinger": {"window": 20, "num_std": 2.0},
            "garch_inputs": {"window": 20},
        }

    features = pd.DataFrame(index=df.index)

    if "returns" in config:
        for period in config["returns"]:
            features[f"return_{period}"] = compute_returns(df, periods=period)
            features[f"log_return_{period}"] = compute_returns(
                df, periods=period, log_returns=True
            )

    if "volatility" in config:
        vol_config = config["volatility"]
        windows = vol_config.get("windows", [20])
        method = vol_config.get("method", "std")
        for window in windows:
            features[f"volatility_{method}_{window}"] = compute_volatility(
                df, window=window, method=method
            )

    if "ema" in config:
        for span in config["ema"]:
            features[f"ema_{span}"] = compute_ema(df["close"], span)

    if "sma" in config:
        for window in config["sma"]:
            features[f"sma_{window}"] = compute_sma(df["close"], window)

    if "atr" in config:
        for window in config["atr"]:
            features[f"atr_{window}"] = compute_atr(df, window)

    if "rsi" in config:
        for window in config["rsi"]:
            features[f"rsi_{window}"] = compute_rsi(df["close"], window)

    if config.get("macd"):
        macd_df = compute_macd(df["close"])
        features = pd.concat([features, macd_df], axis=1)

    if "bollinger" in config:
        bb_config = config["bollinger"]
        bb_df = compute_bollinger_bands(
            df["close"],
            window=bb_config.get("window", 20),
            num_std=bb_config.get("num_std", 2.0),
        )
        features = pd.concat([features, bb_df], axis=1)

    if "garch_inputs" in config:
        garch_df = compute_garch_inputs(df, window=config["garch_inputs"].get("window", 20))
        features = pd.concat([features, garch_df], axis=1)

    return features


def compute_indicators(timeframes: dict[Timeframe, pd.DataFrame]) -> dict[Timeframe, dict[str, float]]:
    """Compute latest values of all indicators for all timeframes."""
    results = {}
    for tf, df in timeframes.items():
        if df.empty or len(df) < 2:
            results[tf] = {}
            continue

        close = df["close"]
        ema_20_series = compute_ema(close, 20)
        ema_20 = ema_20_series.iloc[-1] if not ema_20_series.empty else np.nan
        
        ema_50_series = compute_ema(close, 50)
        ema_50 = ema_50_series.iloc[-1] if not ema_50_series.empty else np.nan
        
        ema_200_series = compute_ema(close, 200)
        ema_200 = ema_200_series.iloc[-1] if not ema_200_series.empty else np.nan

        adx_series = compute_adx(df, 14)
        adx = adx_series.iloc[-1] if not adx_series.empty else np.nan

        rsi_series = compute_rsi(close, 14)
        rsi = rsi_series.iloc[-1] if not rsi_series.empty else np.nan

        stoch = compute_stochastic(df, 14, 3)
        stoch_k = stoch["stoch_k"].iloc[-1] if not stoch.empty else np.nan
        stoch_d = stoch["stoch_d"].iloc[-1] if not stoch.empty else np.nan

        macd_df = compute_macd(close, 12, 26, 9)
        macd = macd_df["macd"].iloc[-1] if not macd_df.empty else np.nan
        macd_sig = macd_df["macd_signal"].iloc[-1] if not macd_df.empty else np.nan
        macd_hist = macd_df["macd_hist"].iloc[-1] if not macd_df.empty else np.nan

        atr_series = compute_atr(df, 14)
        atr = atr_series.iloc[-1] if not atr_series.empty else np.nan

        bb = compute_bollinger_bands(close, 20, 2.0)
        bb_mid = bb["bb_middle"].iloc[-1] if not bb.empty else np.nan
        bb_up = bb["bb_upper"].iloc[-1] if not bb.empty else np.nan
        bb_low = bb["bb_lower"].iloc[-1] if not bb.empty else np.nan
        bb_wid = bb["bb_width"].iloc[-1] if not bb.empty else np.nan

        obv_series = compute_obv(df)
        obv = obv_series.iloc[-1] if not obv_series.empty else np.nan

        vwap_series = compute_vwap(df)
        vwap = vwap_series.iloc[-1] if not vwap_series.empty else np.nan

        sr = compute_sr_distance(df, 3)
        support = sr["support"].iloc[-1] if not sr.empty else np.nan
        resistance = sr["resistance"].iloc[-1] if not sr.empty else np.nan
        dist_support = sr["dist_support"].iloc[-1] if not sr.empty else np.nan
        dist_resistance = sr["dist_resistance"].iloc[-1] if not sr.empty else np.nan

        results[tf] = {
            "ema_20": float(ema_20) if not pd.isna(ema_20) else 0.0,
            "ema_50": float(ema_50) if not pd.isna(ema_50) else 0.0,
            "ema_200": float(ema_200) if not pd.isna(ema_200) else 0.0,
            "adx": float(adx) if not pd.isna(adx) else 0.0,
            "rsi": float(rsi) if not pd.isna(rsi) else 50.0,
            "stoch_k": float(stoch_k) if not pd.isna(stoch_k) else 50.0,
            "stoch_d": float(stoch_d) if not pd.isna(stoch_d) else 50.0,
            "macd": float(macd) if not pd.isna(macd) else 0.0,
            "macd_signal": float(macd_sig) if not pd.isna(macd_sig) else 0.0,
            "macd_hist": float(macd_hist) if not pd.isna(macd_hist) else 0.0,
            "atr": float(atr) if not pd.isna(atr) else 0.0,
            "bb_middle": float(bb_mid) if not pd.isna(bb_mid) else 0.0,
            "bb_upper": float(bb_up) if not pd.isna(bb_up) else 0.0,
            "bb_lower": float(bb_low) if not pd.isna(bb_low) else 0.0,
            "bb_width": float(bb_wid) if not pd.isna(bb_wid) else 0.0,
            "obv": float(obv) if not pd.isna(obv) else 0.0,
            "vwap": float(vwap) if not pd.isna(vwap) else 0.0,
            "support": float(support) if not pd.isna(support) else 0.0,
            "resistance": float(resistance) if not pd.isna(resistance) else 0.0,
            "dist_support": float(dist_support) if not pd.isna(dist_support) else 0.0,
            "dist_resistance": float(dist_resistance) if not pd.isna(dist_resistance) else 0.0,
        }

    return results
