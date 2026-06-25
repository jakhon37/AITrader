"""OHLCV fetch wrapper used by the live scheduler loop."""

from __future__ import annotations

from typing import Optional

from src.core.contracts import Instrument, OHLCVBar, Timeframe
from src.core.exceptions import DataError
from src.data.feeds.base import OHLCVFeed
from src.data.feeds.dukascopy import DukascopyFeed
from src.data.scheduler.bars import normalize_wick


def create_ohlcv_feed(source: str = "dukascopy") -> OHLCVFeed:
    """Factory for the configured OHLCV feed."""
    if source == "dukascopy":
        return DukascopyFeed()
    raise DataError(f"Unsupported data source: {source!r}. Use 'dukascopy'.")


class OHLCVFetcher:
    """Backward-compatible wrapper around OHLCVFeed for scheduler and tests."""

    def __init__(self, feed: Optional[OHLCVFeed] = None, source: str = "dukascopy") -> None:
        self._feed = feed or create_ohlcv_feed(source)

    def fetch_live_bars(
        self,
        instrument: Instrument,
        timeframe: Timeframe,
    ) -> tuple[OHLCVBar, Optional[OHLCVBar]]:
        completed, active = self._feed.fetch_live_bars(instrument, timeframe)
        completed = normalize_wick(completed)
        if active is not None:
            active = normalize_wick(active)
        return completed, active

    def fetch_latest_bar(
        self,
        instrument: Instrument,
        timeframe: Timeframe,
    ) -> OHLCVBar:
        completed_bar, _ = self.fetch_live_bars(instrument, timeframe)
        return completed_bar