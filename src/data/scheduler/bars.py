"""OHLCV bar normalization for chart libraries."""

from __future__ import annotations

from src.core.contracts import OHLCVBar
from src.core.session import pip_size_for


def normalize_wick(bar: OHLCVBar) -> OHLCVBar:
    """Ensure open/close sit inside [low, high] for chart libraries."""
    low = min(bar.open, bar.high, bar.low, bar.close)
    high = max(bar.open, bar.high, bar.low, bar.close)
    if high == low:
        pip = pip_size_for(bar.instrument)
        high = bar.close + pip / 2
        low = bar.close - pip / 2
    return bar.model_copy(update={"high": high, "low": low})