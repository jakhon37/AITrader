"""Technical indicators for feature engineering.

Provides commonly used technical indicators:
- Returns (simple, log)
- Volatility (rolling std, Parkinson, Garman-Klass)
- Moving averages (EMA, SMA)
- ATR (Average True Range)
- RSI (Relative Strength Index)
- MACD (Moving Average Convergence Divergence)
- Bollinger Bands
- GARCH-related inputs (for volatility modeling)
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd


def compute_returns(
    df: pd.DataFrame,
    price_col: str = "close",
    periods: int = 1,
    log_returns: bool = False,
) -> pd.Series:
    """Compute simple or log returns.

    Args:
        df: OHLCV DataFrame
        price_col: Column to compute returns on
        periods: Number of periods for return calculation
        log_returns: If True, compute log returns; else simple returns

    Returns:
        Series of returns
    """
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
    """Compute rolling volatility.

    Args:
        df: OHLCV DataFrame
        window: Rolling window size
        method: 'std' (close-to-close), 'parkinson', or 'garman_klass'
        price_col: Price column for 'std' method

    Returns:
        Series of volatility estimates
    """
    if method == "std":
        returns = compute_returns(df, price_col=price_col, log_returns=True)
        return returns.rolling(window).std() * np.sqrt(252)  # Annualized

    elif method == "parkinson":
        # Parkinson volatility using high/low
        hl = np.log(df["high"] / df["low"])
        return (hl**2 / (4 * np.log(2))).rolling(window).mean().apply(np.sqrt) * np.sqrt(
            252
        )

    elif method == "garman_klass":
        # Garman-Klass volatility
        hl = np.log(df["high"] / df["low"]) ** 2
        co = np.log(df["close"] / df["open"]) ** 2
        gk = 0.5 * hl - (2 * np.log(2) - 1) * co
        return gk.rolling(window).mean().apply(np.sqrt) * np.sqrt(252)

    else:
        raise ValueError(f"Unknown volatility method: {method}")


def compute_ema(series: pd.Series, span: int) -> pd.Series:
    """Compute Exponential Moving Average.

    Args:
        series: Input series (typically close prices)
        span: EMA span (equivalent to N-period EMA)

    Returns:
        Series of EMA values
    """
    return series.ewm(span=span, adjust=False).mean()


def compute_sma(series: pd.Series, window: int) -> pd.Series:
    """Compute Simple Moving Average.

    Args:
        series: Input series
        window: Window size

    Returns:
        Series of SMA values
    """
    return series.rolling(window=window).mean()


def compute_atr(df: pd.DataFrame, window: int = 14) -> pd.Series:
    """Compute Average True Range.

    Args:
        df: OHLCV DataFrame
        window: Window for ATR calculation

    Returns:
        Series of ATR values
    """
    high = df["high"]
    low = df["low"]
    close_prev = df["close"].shift(1)

    tr1 = high - low
    tr2 = (high - close_prev).abs()
    tr3 = (low - close_prev).abs()

    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return true_range.rolling(window=window).mean()


def compute_rsi(series: pd.Series, window: int = 14) -> pd.Series:
    """Compute Relative Strength Index.

    Args:
        series: Price series (typically close)
        window: RSI window

    Returns:
        Series of RSI values (0-100)
    """
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
    """Compute MACD (Moving Average Convergence Divergence).

    Args:
        series: Price series (typically close)
        fast: Fast EMA period
        slow: Slow EMA period
        signal: Signal line EMA period

    Returns:
        DataFrame with columns: macd, signal, histogram
    """
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
    """Compute Bollinger Bands.

    Args:
        series: Price series
        window: Window for moving average
        num_std: Number of standard deviations for bands

    Returns:
        DataFrame with columns: bb_middle, bb_upper, bb_lower, bb_width
    """
    middle = compute_sma(series, window)
    std = series.rolling(window=window).std()

    upper = middle + (std * num_std)
    lower = middle - (std * num_std)
    width = (upper - lower) / middle  # Normalized width

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
    """Compute GARCH-related input features.

    Args:
        df: OHLCV DataFrame
        window: Rolling window for features
        price_col: Price column

    Returns:
        DataFrame with GARCH-related features
    """
    returns = compute_returns(df, price_col=price_col, log_returns=True)

    # Rolling statistics
    ret_mean = returns.rolling(window).mean()
    ret_std = returns.rolling(window).std()
    ret_skew = returns.rolling(window).skew()
    ret_kurt = returns.rolling(window).kurt()

    # Squared returns (volatility proxy)
    ret_squared = returns**2

    # ARCH effects (autocorrelation of squared returns)
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


def compute_all_indicators(
    df: pd.DataFrame,
    config: Optional[dict] = None,
) -> pd.DataFrame:
    """Compute all technical indicators based on config.

    Args:
        df: OHLCV DataFrame with DatetimeIndex
        config: Optional dict specifying which indicators and params

    Returns:
        DataFrame with all computed indicators
    """
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

    # Returns
    if "returns" in config:
        for period in config["returns"]:
            features[f"return_{period}"] = compute_returns(df, periods=period)
            features[f"log_return_{period}"] = compute_returns(
                df, periods=period, log_returns=True
            )

    # Volatility
    if "volatility" in config:
        vol_config = config["volatility"]
        windows = vol_config.get("windows", [20])
        method = vol_config.get("method", "std")
        for window in windows:
            features[f"volatility_{method}_{window}"] = compute_volatility(
                df, window=window, method=method
            )

    # EMAs
    if "ema" in config:
        for span in config["ema"]:
            features[f"ema_{span}"] = compute_ema(df["close"], span)

    # SMAs
    if "sma" in config:
        for window in config["sma"]:
            features[f"sma_{window}"] = compute_sma(df["close"], window)

    # ATR
    if "atr" in config:
        for window in config["atr"]:
            features[f"atr_{window}"] = compute_atr(df, window)

    # RSI
    if "rsi" in config:
        for window in config["rsi"]:
            features[f"rsi_{window}"] = compute_rsi(df["close"], window)

    # MACD
    if config.get("macd"):
        macd_df = compute_macd(df["close"])
        features = pd.concat([features, macd_df], axis=1)

    # Bollinger Bands
    if "bollinger" in config:
        bb_config = config["bollinger"]
        bb_df = compute_bollinger_bands(
            df["close"],
            window=bb_config.get("window", 20),
            num_std=bb_config.get("num_std", 2.0),
        )
        features = pd.concat([features, bb_df], axis=1)

    # GARCH inputs
    if "garch_inputs" in config:
        garch_df = compute_garch_inputs(df, window=config["garch_inputs"].get("window", 20))
        features = pd.concat([features, garch_df], axis=1)

    return features
