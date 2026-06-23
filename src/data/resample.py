"""D02-DATA — Timeframe resampling utility."""

from __future__ import annotations

import pandas as pd
from src.core.logging import get_logger

_log = get_logger("D02-DATA")


def resample_4h(df_1h: pd.DataFrame) -> pd.DataFrame:
    """Resample 1-hour OHLCV data to 4-hour timeframe.

    Ensures standard UTC boundaries: 00:00, 04:00, 08:00, 12:00, 16:00, 20:00.
    Drops partial bars at session edges (e.g. weekend close or holidays) to
    prevent merging bars across weekend gap.

    Parameters
    ----------
    df_1h:
        DataFrame with DatetimeIndex and columns: open, high, low, close, volume.

    Returns
    -------
    pd.DataFrame
        4-hour resampled OHLCV DataFrame.
    """
    if df_1h.empty:
        return pd.DataFrame()

    # Verify input structure
    if not isinstance(df_1h.index, pd.DatetimeIndex):
        raise ValueError("Input DataFrame index must be a DatetimeIndex")

    # Resample using left-closed, left-labeled bins
    resampler = df_1h.resample("4h", closed="left", label="left")

    resampled = pd.DataFrame()
    resampled["open"] = resampler["open"].first()
    resampled["high"] = resampler["high"].max()
    resampled["low"] = resampler["low"].min()
    resampled["close"] = resampler["close"].last()
    resampled["volume"] = resampler["volume"].sum()
    
    # Track count of underlying 1h bars in each 4h bar
    bar_counts = resampler["close"].count()

    # Drop resampled bars where we don't have exactly 4 underlying hours
    # This automatically discards weekend gap bridging or sparse holiday candles
    resampled = resampled[bar_counts == 4].dropna()

    _log.debug(
        "resample_4h_complete",
        input_bars=len(df_1h),
        output_bars=len(resampled),
    )
    return resampled
