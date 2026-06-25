"""D02-DATA — Parquet merge helpers that prevent flat-bar downgrades."""

from __future__ import annotations

import pandas as pd


def bar_spread(row: pd.Series) -> float:
    return float(row["high"]) - float(row["low"])


def is_flat_bar(row: pd.Series) -> bool:
    return bar_spread(row) <= 0


def merge_ohlcv_without_downgrade(existing: pd.DataFrame, incoming: pd.DataFrame) -> pd.DataFrame:
    """Merge incoming rows into existing, never replacing wicks with flat bars."""
    if existing.empty:
        return incoming.copy()
    if incoming.empty:
        return existing.copy()

    combined = pd.concat([existing, incoming])
    combined = combined[~combined.index.duplicated(keep="last")]
    combined.sort_index(inplace=True)

    # Re-apply anti-downgrade for overlapping timestamps
    overlap = existing.index.intersection(incoming.index)
    for ts in overlap:
        old = existing.loc[ts]
        new = incoming.loc[ts]
        if is_flat_bar(new) and not is_flat_bar(old):
            combined.loc[ts, "open"] = old["open"]
            combined.loc[ts, "high"] = max(float(old["high"]), float(new["close"]))
            combined.loc[ts, "low"] = min(float(old["low"]), float(new["close"]))
            combined.loc[ts, "close"] = new["close"]
            combined.loc[ts, "volume"] = max(float(old.get("volume", 0)), float(new.get("volume", 0)))
        elif not is_flat_bar(new) and is_flat_bar(old):
            combined.loc[ts, "open"] = new["open"]
            combined.loc[ts, "high"] = new["high"]
            combined.loc[ts, "low"] = new["low"]
            combined.loc[ts, "close"] = new["close"]
            combined.loc[ts, "volume"] = new["volume"]
        elif not is_flat_bar(new) and not is_flat_bar(old):
            combined.loc[ts, "high"] = max(float(old["high"]), float(new["high"]))
            combined.loc[ts, "low"] = min(float(old["low"]), float(new["low"]))
            combined.loc[ts, "volume"] = max(float(old.get("volume", 0)), float(new.get("volume", 0)))

    return combined